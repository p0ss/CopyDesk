// scraper/extractors.js
const crypto = require('crypto');
const syllable = require('syllable');
const cssesc = require('cssesc');

async function extractFragment({
  $heading,
  $content,
  $,
  url,
  breadcrumbs,
  pageTitle,
  page
}) {
  // Generate unique ID
  const headingText = $heading.text().trim();
  const contentText = $content.text().trim();
  const id = crypto.createHash('md5')
    .update(url + headingText + contentText)
    .digest('hex');
  
  // Build hierarchy
  const headingLevel = parseInt($heading[0].name.substring(1));
  const hierarchyLevels = {};
  
  // Assign to appropriate hierarchy level
  if (headingLevel === 1) {
    hierarchyLevels.hierarchy_lvl0 = headingText;
  } else if (headingLevel === 2) {
    hierarchyLevels.hierarchy_lvl0 = breadcrumbs[breadcrumbs.length - 1] || pageTitle;
    hierarchyLevels.hierarchy_lvl1 = headingText;
  } else if (headingLevel === 3) {
    hierarchyLevels.hierarchy_lvl0 = breadcrumbs[breadcrumbs.length - 1] || pageTitle;
    hierarchyLevels.hierarchy_lvl1 = $heading.prevAll('h2').first().text() || '';
    hierarchyLevels.hierarchy_lvl2 = headingText;
  } else {
    hierarchyLevels.hierarchy_lvl0 = breadcrumbs[breadcrumbs.length - 1] || pageTitle;
    hierarchyLevels.hierarchy_lvl1 = $heading.prevAll('h2').first().text() || '';
    hierarchyLevels.hierarchy_lvl2 = $heading.prevAll('h3').first().text() || '';
    hierarchyLevels.hierarchy_lvl3 = headingText;
  }
  
  // Create container for HTML preservation
  const $container = $('<div class="content-fragment"></div>');
  $container.append($heading.clone());
  $container.append($content.clone());
  
  // Extract styles
  const styles = await extractStyles($, page);
  const classes = extractClasses($container);
  
  // Extract metadata
  const metadata = extractMetadata($container);
  
  // Build fragment object
  return {
    id,
    url: url + '#' + ($heading.attr('id') || id),
    anchor: $heading.attr('id') || id,
    title: headingText,
    content_text: contentText,
    content_html: $container.html(),
    site_hierarchy: extractSiteHierarchy(url),
    page_hierarchy: [...breadcrumbs, headingText],
    ...hierarchyLevels,
    
    // These will be enriched by taxonomies.js
    life_events: [],
    categories: [],
    states: ['National'], // Default, will be overridden if state-specific
    
    // Metadata
    component_type: detectComponentType($container),
    has_form: $container.find('form').length > 0,
    has_checklist: $container.find('ol, ul.checklist').length > 0,
    reading_level: calculateReadingLevel(contentText),
    last_modified: new Date().getTime(),
    
    // Presentation
    styles_raw: styles,
    classes: classes,
    
    // Search optimization
    search_keywords: extractKeywords(contentText),
    popularity_score: calculatePopularityScore($container, headingLevel)
  };
}

function extractSiteHierarchy(url) {
  try {
    const urlObj = new URL(url);
    return [
      urlObj.hostname,
      ...urlObj.pathname.split('/').filter(p => p)
    ];
  } catch {
    return [];
  }
}

async function extractStyles($, page) {
  // Get all stylesheets
  const styleSheets = [];
  
  // Inline styles
  $('style').each((i, elem) => {
    styleSheets.push($(elem).html());
  });
  
  // Get computed styles for specific classes if needed
  try {
    const computedStyles = await page.evaluate(() => {
      const styles = {};
      const importantClasses = [
        '.medicare-card', '.info-box', '.step-list',
        '.alert', '.warning', '.checklist'
      ];
      
      importantClasses.forEach(className => {
        const elem = document.querySelector(className);
        if (elem) {
          const computed = window.getComputedStyle(elem);
          styles[className] = {
            background: computed.backgroundColor,
            color: computed.color,
            padding: computed.padding,
            border: computed.border,
            fontSize: computed.fontSize
          };
        }
      });
      
      return styles;
    });
    
    return {
      inline: styleSheets,
      computed: computedStyles
    };
  } catch {
    return { inline: styleSheets };
  }
}

function extractClasses($container) {
  const classes = new Set();
  
  $container.find('*').each((i, elem) => {
    const classList = $(elem).attr('class');
    if (classList) {
      classList.split(' ').forEach(c => classes.add(c.trim()));
    }
  });
  
  return Array.from(classes);
}

function detectComponentType($container) {
  if ($container.find('form').length) return 'form';
  if ($container.find('table').length) return 'table';
  if ($container.find('.checklist, ol.steps').length) return 'checklist';
  if ($container.find('.alert, [role="alert"]').length) return 'alert';
  if ($container.find('.card, .info-box').length) return 'card';
  if ($container.find('video, iframe[src*="youtube"]').length) return 'video';
  return 'content';
}

function extractMetadata($container) {
  return {
    wordCount: $container.text().split(/\s+/).length,
    hasImages: $container.find('img').length > 0,
    hasLinks: $container.find('a').length > 0,
    linkCount: $container.find('a').length,
    listCount: $container.find('ul, ol').length,
    emphasisCount: $container.find('strong, b, em, i').length
  };
}

function calculateReadingLevel(text) {
  // Using syllable package for accurate syllable counting
  const words = text.split(/\s+/).filter(w => w.length > 0);
  const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 0);
  const syllableCount = syllable(text);
  
  if (sentences.length === 0 || words.length === 0) return 12;
  
  // Flesch-Kincaid Grade Level
  const score = 0.39 * (words.length / sentences.length) + 
                11.8 * (syllableCount / words.length) - 15.59;
  
  return Math.max(1, Math.min(12, Math.round(score)));
}

function extractKeywords(text) {
  // Simple keyword extraction
  const stopWords = new Set([
    'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but',
    'in', 'with', 'to', 'for', 'of', 'as', 'by', 'that', 'this',
    'it', 'from', 'be', 'are', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might'
  ]);
  
  const words = text.toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .split(/\s+/)
    .filter(word => word.length > 3 && !stopWords.has(word));
  
  // Count frequencies
  const frequencies = {};
  words.forEach(word => {
    frequencies[word] = (frequencies[word] || 0) + 1;
  });
  
  // Return top keywords
  return Object.entries(frequencies)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([word]) => word);
}

function calculatePopularityScore($container, headingLevel) {
  let score = 100;
  
  // Heading level impacts importance
  score -= (headingLevel - 1) * 10;
  
  // Content indicators
  if ($container.find('form').length) score += 20;
  if ($container.find('.alert, .warning').length) score += 15;
  if ($container.find('ol, ul').length) score += 10;
  if ($container.find('table').length) score += 10;
  
  // Length indicator (not too short, not too long)
  const wordCount = $container.text().split(/\s+/).length;
  if (wordCount > 50 && wordCount < 500) score += 10;
  
  return Math.max(0, Math.min(100, score));
}

function cssPath(el) {
  // Robust unique selector with cssesc for proper escaping
  let path = '';
  while (el.parent().length && el[0].tagName.toLowerCase() !== 'html') {
    const tag = el[0].tagName.toLowerCase();
    const id = el.attr('id');
    const classes = el.attr('class');
    
    if (id) {
      // If element has ID, that's unique enough
      path = `${tag}#${cssesc(id, {isIdentifier: true})}` + (path ? ' > ' + path : '');
      break;
    } else if (classes) {
      // Use first class if available
      const firstClass = classes.split(' ')[0];
      path = `${tag}.${cssesc(firstClass, {isIdentifier: true})}` + (path ? ' > ' + path : '');
    } else {
      // Just tag name
      path = tag + (path ? ' > ' + path : '');
    }
    
    el = el.parent();
  }
  return path;
}

module.exports = {
  extractFragment,
  extractStyles,
  extractClasses,
  detectComponentType,
  extractMetadata,
  calculateReadingLevel,
  extractKeywords,
  calculatePopularityScore,
  cssPath
};