// scraper/taxonomies.js
const fs = require('fs').promises;
const path = require('path');

// Load taxonomy data
let taxonomyData = null;

async function loadTaxonomyData() {
  if (!taxonomyData) {
    try {
      const dataPath = path.join(__dirname, '../data/seed-taxonomies.json');
      const data = await fs.readFile(dataPath, 'utf8');
      taxonomyData = JSON.parse(data);
    } catch (error) {
      console.error('Failed to load taxonomy data:', error);
      taxonomyData = getDefaultTaxonomyData();
    }
  }
  return taxonomyData;
}

function getDefaultTaxonomyData() {
  return {
    lifeEvents: {
      'Having a baby': {
        keywords: ['pregnancy', 'pregnant', 'baby', 'birth', 'maternity', 'paternity', 'newborn', 'expecting', 'prenatal', 'postnatal', 'midwife', 'obstetric'],
        relatedCategories: ['Raising Kids', 'Health and Disability'],
        stages: {
          'Before your baby arrives': ['pregnancy', 'expecting', 'prenatal', 'before birth'],
          'When your baby arrives': ['birth', 'newborn', 'hospital', 'delivery'],
          'As your baby grows': ['infant', 'toddler', 'child care', 'immunisation']
        }
      },
      'Work': {
        keywords: ['employment', 'job', 'career', 'workplace', 'employer', 'employee', 'salary', 'wages', 'redundancy', 'unemployment'],
        relatedCategories: ['Education', 'Money and Finance']
      },
      'Ageing': {
        keywords: ['retirement', 'pension', 'senior', 'elderly', 'aged care', 'super', 'aged', 'older'],
        relatedCategories: ['Health and Disability', 'Living Arrangements']
      },
      'Education': {
        keywords: ['school', 'university', 'tafe', 'training', 'student', 'study', 'qualification', 'degree', 'apprentice'],
        relatedCategories: ['Work', 'Raising Kids']
      }
    },
    
    categories: {
      'Health and Disability': ['health', 'medical', 'medicare', 'disability', 'ndis', 'mental health', 'hospital', 'doctor', 'treatment'],
      'Raising Kids': ['child', 'children', 'parenting', 'family', 'school', 'childcare', 'youth'],
      'Money and Finance': ['payment', 'benefit', 'tax', 'income', 'financial', 'money', 'debt', 'loan'],
      'Living Arrangements': ['housing', 'rent', 'home', 'accommodation', 'homeless', 'tenant']
    },
    
    providers: {
      'Federal Government': {
        'Services Australia': ['centrelink', 'medicare', 'child support'],
        'Australian Taxation Office': ['tax', 'ato', 'gst', 'tfn'],
        'Department of Health': ['health.gov.au', 'immunisation', 'aged care'],
        'Department of Education': ['education.gov.au', 'skills', 'training']
      },
      'State Government': {
        'NSW': ['nsw.gov.au', 'service.nsw'],
        'VIC': ['vic.gov.au', 'service.vic'],
        'QLD': ['qld.gov.au', 'queensland'],
        'WA': ['wa.gov.au', 'western australia'],
        'SA': ['sa.gov.au', 'south australia'],
        'TAS': ['tas.gov.au', 'tasmania'],
        'ACT': ['act.gov.au', 'canberra'],
        'NT': ['nt.gov.au', 'northern territory']
      }
    },
    
    stageVariants: {
      'Having a baby': {
        'Adopting a child': ['adoption', 'adopt', 'foster'],
        'Surrogacy': ['surrogate', 'surrogacy'],
        'IVF': ['ivf', 'fertility', 'assisted reproduction'],
        'Multiple births': ['twins', 'triplets', 'multiple'],
        'Premature birth': ['premature', 'preterm', 'nicu'],
        'Stillborn baby': ['stillborn', 'stillbirth', 'loss']
      }
    }
  };
}

async function enrichWithTaxonomy(fragment) {
  const taxonomy = await loadTaxonomyData();
  const contentLower = (fragment.content_text + ' ' + fragment.title).toLowerCase();
  const url = fragment.url.toLowerCase();
  
  // Detect life events
  fragment.life_events = detectLifeEvents(contentLower, taxonomy.lifeEvents);
  
  // Detect categories
  fragment.categories = detectCategories(contentLower, taxonomy.categories);
  
  // Detect stage if life event is detected
  if (fragment.life_events.includes('Having a baby')) {
    fragment.stage = detectStage(contentLower, taxonomy.lifeEvents['Having a baby'].stages);
    fragment.stage_variant = detectStageVariant(contentLower, taxonomy.stageVariants['Having a baby']);
  }
  
  // Detect provider and governance
  const providerInfo = detectProvider(url, contentLower, taxonomy.providers);
  fragment.provider = providerInfo.provider;
  fragment.governance = providerInfo.governance;
  
  // Detect state
  fragment.states = detectStates(url, contentLower, fragment.site_hierarchy);
  
  // Add task order if it's a checklist item
  if (fragment.has_checklist || fragment.component_type === 'checklist') {
    fragment.task_order = detectTaskOrder(fragment.content_html);
  }
  
  return fragment;
}

function detectLifeEvents(content, lifeEventsData) {
  const detectedEvents = [];
  
  for (const [event, data] of Object.entries(lifeEventsData)) {
    const keywordMatches = data.keywords.filter(keyword => 
      content.includes(keyword)
    ).length;
    
    if (keywordMatches >= 2 || (keywordMatches === 1 && data.keywords.some(k => content.includes(k) && k.length > 6))) {
      detectedEvents.push(event);
    }
  }
  
  return detectedEvents;
}

function detectCategories(content, categoriesData) {
  const detectedCategories = [];
  
  for (const [category, keywords] of Object.entries(categoriesData)) {
    const keywordMatches = keywords.filter(keyword => 
      content.includes(keyword)
    ).length;
    
    if (keywordMatches >= 2) {
      detectedCategories.push(category);
    }
  }
  
  return detectedCategories;
}

function detectStage(content, stages) {
  for (const [stage, keywords] of Object.entries(stages)) {
    if (keywords.some(keyword => content.includes(keyword))) {
      return stage;
    }
  }
  return null;
}

function detectStageVariant(content, variants) {
  for (const [variant, keywords] of Object.entries(variants)) {
    if (keywords.some(keyword => content.includes(keyword))) {
      return variant;
    }
  }
  return 'No';
}

function detectProvider(url, content, providersData) {
  // Check URL patterns first
  for (const [governance, providers] of Object.entries(providersData)) {
    for (const [provider, patterns] of Object.entries(providers)) {
      if (patterns.some(pattern => url.includes(pattern) || content.includes(pattern))) {
        return { governance, provider };
      }
    }
  }
  
  // Default based on domain
  if (url.includes('.gov.au')) {
    if (url.includes('australia.gov.au') || url.includes('my.gov.au')) {
      return { governance: 'Federal Government', provider: 'Australian Government' };
    }
    // Try to detect state from URL
    const stateMatch = url.match(/\.(\w{2,3})\.gov\.au/);
    if (stateMatch) {
      const state = stateMatch[1].toUpperCase();
      return { governance: 'State Government', provider: `${state} Government` };
    }
  }
  
  return { governance: 'Non-Government', provider: 'External Provider' };
}

function detectStates(url, content, siteHierarchy) {
  const states = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT'];
  const detectedStates = [];
  
  // Check URL and hierarchy
  const urlAndHierarchy = url + ' ' + siteHierarchy.join(' ');
  states.forEach(state => {
    if (urlAndHierarchy.includes(state.toLowerCase()) || 
        urlAndHierarchy.includes(getStateName(state).toLowerCase())) {
      detectedStates.push(state);
    }
  });
  
  // Check content for state mentions
  states.forEach(state => {
    const statePattern = new RegExp(`\\b${state}\\b|\\b${getStateName(state)}\\b`, 'i');
    if (statePattern.test(content)) {
      if (!detectedStates.includes(state)) {
        detectedStates.push(state);
      }
    }
  });
  
  return detectedStates.length > 0 ? detectedStates : ['National'];
}

function getStateName(code) {
  const stateNames = {
    'NSW': 'New South Wales',
    'VIC': 'Victoria',
    'QLD': 'Queensland',
    'WA': 'Western Australia',
    'SA': 'South Australia',
    'TAS': 'Tasmania',
    'ACT': 'Australian Capital Territory',
    'NT': 'Northern Territory'
  };
  return stateNames[code] || code;
}

function detectTaskOrder(html) {
  // Look for numbered lists or step indicators
  const match = html.match(/(?:step|stage)\s*(\d+)/i);
  if (match) {
    return parseInt(match[1]);
  }
  
  // Check for ordered list position
  const olMatch = html.match(/<li[^>]*>[\s\S]*?<\/li>/g);
  if (olMatch) {
    return olMatch.length;
  }
  
  return null;
}

module.exports = {
  enrichWithTaxonomy,
  loadTaxonomyData
};