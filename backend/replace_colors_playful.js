const fs = require('fs');
const path = require('path');

const replacements = {
  // Brand Blue
  '#2563EB': '#1CB0F6',
  '#1D4ED8': '#1899D6',
  '#EFF6FF': '#DDF4FF',
  
  // Backgrounds
  '#FAFAFA': '#F7F7F7',
  '#F1F5F9': '#E5E5E5',
  
  // Text
  '#0F172A': '#3C3C3C',
  '#64748B': '#777777',
  '#94A3B8': '#AFAFAF',
  
  // Success (Green)
  '#16A34A': '#58CC02',
  '#15803D': '#46A302',
  '#F0FDF4': '#D7FFB8',
  
  // Warning (Yellow)
  '#F59E0B': '#FFC800',
  '#FFFBEB': '#FFF0B3',
  
  // Error (Red)
  '#DC2626': '#FF4B4B',
  '#FEF2F2': '#FFD1D1',

  // Utility Class Adjustments for Bubbly Design
  'shadow-2xs': 'elevation-1',
  'shadow-xs': 'elevation-2',
  'shadow-sm': 'elevation-3',
  'shadow-md': 'elevation-4',
  
  'rounded-2xl': 'rounded-[1.5rem]',
  'rounded-3xl': 'rounded-[2rem]',
  'rounded-xl': 'rounded-[1.25rem]',
};

function walk(dir, callback) {
  fs.readdirSync(dir).forEach(file => {
    let filepath = path.join(dir, file);
    let stat = fs.statSync(filepath);
    if (stat.isDirectory() && file !== 'node_modules' && file !== '.git') {
      walk(filepath, callback);
    } else if (stat.isFile() && (filepath.endsWith('.tsx') || filepath.endsWith('.ts') || filepath.endsWith('.jsx') || filepath.endsWith('.js') || filepath.endsWith('.html'))) {
      callback(filepath);
    }
  });
}

const dirPath = path.join(__dirname, '..', 'frontend', 'src');

walk(dirPath, (filepath) => {
  let content = fs.readFileSync(filepath, 'utf8');
  let changed = false;
  
  for (const [oldStr, newStr] of Object.entries(replacements)) {
    // Replace case-insensitively for hex codes
    const regex = new RegExp(oldStr, 'gi');
    if (regex.test(content)) {
      content = content.replace(regex, newStr);
      changed = true;
    }
  }

  if (changed) {
    fs.writeFileSync(filepath, content, 'utf8');
    console.log('Updated:', filepath);
  }
});
