#!/usr/bin/env python3
"""
CopyDesk Web Application - Flask backend with Material Design UI
"""

import asyncio
import json
import yaml
import os
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import logging
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add current directory to path
import sys
sys.path.insert(0, os.getcwd())

# Import evaluators
from evaluators.style_guide.page_evaluator import StyleGuidePageEvaluator
from evaluators.style_guide.section_lead import StyleGuideSectionLead
from evaluators.style_guide.editor import StyleGuideEditor

# Optional: Import fact checker if available
try:
    from evaluators.fact_check.fragment_facts import FragmentFactChecker
except ImportError:
    FragmentFactChecker = None
    logger = logging.getLogger(__name__)
    logger.info("Fact checking module not available - will run without fact checking")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=4)

# Store active evaluations
active_evaluations = {}

def load_config():
    """Load configuration from yaml file"""
    try:
        with open('config/evaluation_config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("Config file not found, using default configuration")
        return {
            "models": {
                "junior": {"provider": "openai", "model": "gpt-3.5-turbo", "temperature": 0.3},
                "senior": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.5},
                "editor": {"provider": "openai", "model": "gpt-4o", "temperature": 0.7}
            },
            "performance": {
                "max_concurrent_juniors": 5,
                "request_timeout": 30
            },
            "reports": {
                "senior": {"priority_threshold": 0.5},
                "editor": {"max_recommendations": 5, "format": "executive", "include_links": True}
            },
            "style_guide": {
                "base_url": "https://www.stylemanual.gov.au",
                "sections": [
                    {
                        "name": "Clear language and writing style",
                        "pages": [
                            "/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice",
                            "/writing-and-designing-content/clear-language-and-writing-style/sentences",
                            "/writing-and-designing-content/clear-language-and-writing-style/voice-and-tone"
                        ]
                    },
                    {
                        "name": "Structuring content",
                        "pages": [
                            "/structuring-content/headings-and-subheadings",
                            "/structuring-content/paragraphs"
                        ]
                    },
                    {
                        "name": "Grammar and punctuation",
                        "pages": [
                            "/grammar-punctuation/punctuation",
                            "/grammar-punctuation/grammar"
                        ]
                    }
                ]
            }
        }

@app.route('/')
def index():
    """Serve the main UI"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get the current configuration"""
    config = load_config()
    # Extract relevant parts for UI
    return jsonify({
        'sections': config.get('style_guide', {}).get('sections', []),
        'models': config.get('models', {}),
        'performance': config.get('performance', {})
    })

@app.route('/api/evaluate', methods=['POST'])
def start_evaluation():
    """Start a new evaluation"""
    data = request.json
    text = data.get('text', '')
    options = data.get('options', {})
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    # Generate evaluation ID
    eval_id = str(uuid.uuid4())
    
    # Start evaluation in background
    executor.submit(run_evaluation_async, eval_id, text, options)
    
    return jsonify({'evaluation_id': eval_id})

def run_evaluation_async(eval_id, text, options):
    """Run evaluation in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_evaluation(eval_id, text, options))

async def run_evaluation(eval_id, text, options):
    """Run the full evaluation pipeline"""
    try:
        config = load_config()
        
        # Store evaluation status
        active_evaluations[eval_id] = {
            'status': 'running',
            'start_time': datetime.now(),
            'text': text[:200] + '...' if len(text) > 200 else text
        }
        
        # Emit start event
        socketio.emit('evaluation_started', {
            'evaluation_id': eval_id,
            'timestamp': datetime.now().isoformat()
        }, room=eval_id)
        
        # Get sections from config
        sections = config['style_guide']['sections']
        selected_sections = options.get('sections', [s['name'] for s in sections])
        
        senior_reports = []
        total_sections = len(selected_sections)
        
        # Process each selected section
        completed_sections = 0
        
        for i, section in enumerate(sections):
            if section['name'] not in selected_sections:
                continue
                
            section_name = section['name']
            section_pages = section.get('pages', [])
            
            # Emit progress update with page details
            socketio.emit('section_started', {
                'evaluation_id': eval_id,
                'section': section_name,
                'progress': (completed_sections / total_sections) * 80,  # Reserve 20% for final synthesis
                'current': completed_sections + 1,
                'total': total_sections,
                'pages': [f"{config['style_guide']['base_url']}{page}" for page in section_pages],
                'total_pages': len(section_pages)
            }, room=eval_id)
            
            # Create section lead evaluator
            section_lead = StyleGuideSectionLead(
                evaluator_id=f"section_{section_name.replace(' ', '_').lower()}",
                section_name=section_name,
                config=config
            )
            
            # Set up page-level callbacks for real-time updates
            def on_page_started(url):
                socketio.emit('page_started', {
                    'evaluation_id': eval_id,
                    'section': section_name,
                    'url': url
                }, room=eval_id)
            
            def on_page_completed(url, score):
                socketio.emit('page_completed', {
                    'evaluation_id': eval_id,
                    'section': section_name,
                    'url': url,
                    'score': score
                }, room=eval_id)
            
            section_lead.on_page_started = on_page_started
            section_lead.on_page_completed = on_page_completed
            
            # Run evaluation for this section
            try:
                section_report = await section_lead.evaluate(text, {'section': section_name})
                senior_reports.append(section_report)
                
                # Check if this section had failures
                failed_evals = section_report.metadata.get('failed_evaluations', 0)
                successful_evals = section_report.metadata.get('successful_evaluations', 0)
                
                if failed_evals > 0:
                    socketio.emit('section_warning', {
                        'evaluation_id': eval_id,
                        'section': section_name,
                        'message': f"{failed_evals} page(s) could not be evaluated (possibly 404 errors)",
                        'failed': failed_evals,
                        'successful': successful_evals
                    }, room=eval_id)
                
                # Emit section complete
                completed_sections += 1
                progress = (completed_sections / total_sections) * 80
                
                socketio.emit('section_completed', {
                    'evaluation_id': eval_id,
                    'section': section_name,
                    'score': section_report.score,
                    'issues': len(section_report.issues),
                    'warnings': failed_evals > 0
                }, room=eval_id)
                
                # Update overall progress
                socketio.emit('progress_update', {
                    'evaluation_id': eval_id,
                    'progress': progress,
                    'message': f'Completed {completed_sections}/{total_sections} sections'
                }, room=eval_id)
                
            except Exception as e:
                logger.error(f"Section {section_name} evaluation failed completely: {e}")
                
                # Create a minimal report for the failed section
                from evaluators.base import EvaluationReport, Issue, Severity
                
                failed_report = EvaluationReport(
                    evaluator_id=f"failed_section_{section_name}",
                    evaluator_role="senior",
                    timestamp=datetime.now(),
                    score=0.0,
                    issues=[Issue(
                        description=f"Section '{section_name}' evaluation failed completely: {str(e)}",
                        severity=Severity.ERROR
                    )],
                    summary=f"Complete section failure: {str(e)}",
                    metadata={
                        'section': section_name,
                        'complete_failure': True,
                        'error': str(e)
                    }
                )
                senior_reports.append(failed_report)
                
                # Emit section failure
                completed_sections += 1
                progress = (completed_sections / total_sections) * 80
                
                socketio.emit('section_failed', {
                    'evaluation_id': eval_id,
                    'section': section_name,
                    'error': str(e)
                }, room=eval_id)
                
                # Update overall progress even for failed sections
                socketio.emit('progress_update', {
                    'evaluation_id': eval_id,
                    'progress': progress,
                    'message': f'Processed {completed_sections}/{total_sections} sections (with errors)'
                }, room=eval_id)
        
        # Editor synthesis
        socketio.emit('editor_started', {
            'evaluation_id': eval_id
        }, room=eval_id)
        
        socketio.emit('progress_update', {
            'evaluation_id': eval_id,
            'progress': 85,
            'message': 'Creating final report...'
        }, room=eval_id)
        
        editor = StyleGuideEditor(
            evaluator_id="chief_editor",
            config=config
        )
        
        final_report = await editor.evaluate(text, {
            'senior_reports': senior_reports,
            'evaluation_type': 'style_guide'
        })
        
        # Generate markdown report
        markdown_report = await editor.generate_markdown_report(final_report)
        
        # Store final report
        active_evaluations[eval_id]['status'] = 'completed'
        active_evaluations[eval_id]['report'] = final_report.to_dict()
        active_evaluations[eval_id]['markdown'] = markdown_report
        active_evaluations[eval_id]['end_time'] = datetime.now()
        
        # Emit completion
        socketio.emit('evaluation_completed', {
            'evaluation_id': eval_id,
            'score': final_report.score,
            'report': final_report.to_dict(),
            'markdown': markdown_report
        }, room=eval_id)
        
    except Exception as e:
        import traceback
        logger.error(f"Evaluation {eval_id} failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        active_evaluations[eval_id]['status'] = 'error'
        active_evaluations[eval_id]['error'] = str(e)
        
        socketio.emit('evaluation_error', {
            'evaluation_id': eval_id,
            'error': str(e)
        }, room=eval_id)

@app.route('/api/evaluation/<eval_id>', methods=['GET'])
def get_evaluation_status(eval_id):
    """Get the status of an evaluation"""
    if eval_id not in active_evaluations:
        return jsonify({'error': 'Evaluation not found'}), 404
    
    eval_data = active_evaluations[eval_id]
    response = {
        'status': eval_data['status'],
        'start_time': eval_data['start_time'].isoformat(),
        'text_preview': eval_data['text']
    }
    
    if eval_data['status'] == 'completed':
        response['report'] = eval_data['report']
        response['markdown'] = eval_data['markdown']
        response['end_time'] = eval_data['end_time'].isoformat()
    elif eval_data['status'] == 'error':
        response['error'] = eval_data['error']
    
    return jsonify(response)

@app.route('/api/evaluations', methods=['GET'])
def list_evaluations():
    """List all evaluations"""
    evaluations = []
    for eval_id, eval_data in active_evaluations.items():
        evaluations.append({
            'id': eval_id,
            'status': eval_data['status'],
            'start_time': eval_data['start_time'].isoformat(),
            'text_preview': eval_data['text']
        })
    
    return jsonify(evaluations)

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to CopyDesk server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('join_evaluation')
def handle_join_evaluation(data):
    """Join an evaluation room for updates"""
    from flask_socketio import join_room
    eval_id = data.get('evaluation_id')
    if eval_id:
        join_room(eval_id)
        emit('joined_evaluation', {'evaluation_id': eval_id})

@socketio.on('leave_evaluation')
def handle_leave_evaluation(data):
    """Leave an evaluation room"""
    from flask_socketio import leave_room
    eval_id = data.get('evaluation_id')
    if eval_id:
        leave_room(eval_id)
        emit('left_evaluation', {'evaluation_id': eval_id})

def main():
    """Main entry point for the CopyDesk web application"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='CopyDesk Web Application')
    parser.add_argument('--host', default=os.getenv('FLASK_HOST', '0.0.0.0'), 
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=int(os.getenv('FLASK_PORT', 5000)), 
                        help='Port to bind to (default: 5000)')
    parser.add_argument('--debug', action='store_true', 
                        default=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
                        help='Run in debug mode')
    args = parser.parse_args()
    
    # Check for API keys
    if not os.getenv('OPENAI_API_KEY') and not os.getenv('GOOGLE_API_KEY'):
        logger.warning("⚠️  No API keys found. Please set OPENAI_API_KEY or GOOGLE_API_KEY")
        logger.warning("   You can copy .env.example to .env and add your keys there")
    
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    # Run the app
    print("🚀 Starting CopyDesk Web Application...")
    print(f"📍 Navigate to: http://localhost:{args.port}")
    print("🛑 Press Ctrl+C to stop")
    
    # Note: In production, use a proper WSGI server like gunicorn or uwsgi
    # For development, we allow the unsafe werkzeug server
    socketio.run(app, debug=args.debug, host=args.host, port=args.port, 
                 allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()