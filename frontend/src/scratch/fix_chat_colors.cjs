const fs = require('fs');

const filePath = 'd:\\Assimovx\\DeepTutor\\frontend\\src\\pages\\ChatPage.tsx';
let content = fs.readFileSync(filePath, 'utf8');

// Fix the mistakes made by the previous replacement script
content = content.replace(/border-\[border\]/g, 'border-border');
content = content.replace(/bg-\[white\]/g, 'bg-white');
content = content.replace(/bg-\[border\]/g, 'bg-border');
content = content.replace(/border-\[info\]/g, 'border-info');
content = content.replace(/ring-\[info\]/g, 'ring-info');

fs.writeFileSync(filePath, content, 'utf8');
console.log('Fixed colors in ChatPage.tsx');
