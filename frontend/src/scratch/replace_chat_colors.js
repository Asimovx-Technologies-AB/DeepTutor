const fs = require('fs');

const filePath = 'd:\\Assimovx\\DeepTutor\\frontend\\src\\pages\\ChatPage.tsx';
let content = fs.readFileSync(filePath, 'utf8');

// Replace cream/orange shades with blue/theme shades
content = content.replace(/#E7E1D8/g, 'var(--color-border)');
content = content.replace(/#FAF8F3/g, 'var(--color-surface-muted)');
content = content.replace(/#F2F0E9/g, 'var(--color-border)');
content = content.replace(/orange-400/g, 'info');

fs.writeFileSync(filePath, content, 'utf8');
console.log('Replaced colors in ChatPage.tsx');
