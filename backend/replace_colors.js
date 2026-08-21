const fs = require('fs');
const path = require('path');

const replacements = {
  '#5B5FEF': '#2563EB', // Primary
  '#4F51D5': '#1D4ED8', // Primary Hover
  '#EEF0FF': '#EFF6FF', // Primary Soft
  '#F8FAFC': '#FAFAFA', // Background
  '#475569': '#64748B', // Text Secondary
  '#4F8A68': '#16A34A', // Success
  '#35654B': '#15803D', // Success Dark
  '#E3F0E5': '#F0FDF4', // Success Soft
  '#D99A32': '#F59E0B', // Warning
  '#FFF3D8': '#FFFBEB', // Warning Soft
  '#C85C52': '#DC2626', // Error
  '#FBE7E4': '#FEF2F2', // Error Soft
  '#E2E8F0': '#E2E8F0', // Border (unchanged)
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
