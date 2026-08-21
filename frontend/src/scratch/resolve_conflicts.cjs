const fs = require('fs');

const files = [
  'd:\\Assimovx\\DeepTutor\\frontend\\src\\pages\\ChatPage.tsx',
  'd:\\Assimovx\\DeepTutor\\frontend\\src\\pages\\QuizPage.tsx',
  'd:\\Assimovx\\DeepTutor\\frontend\\src\\pages\\FlashcardsPage.tsx',
  'd:\\Assimovx\\DeepTutor\\frontend\\src\\pages\\QuizResultPage.tsx',
];

for (const file of files) {
  if (!fs.existsSync(file)) continue;
  let content = fs.readFileSync(file, 'utf8');
  
  const conflictRegex = /<<<<<<< HEAD\n([\s\S]*?)=======\n([\s\S]*?)>>>>>>> [a-f0-9]+\n/g;
  
  let match;
  while ((match = conflictRegex.exec(content)) !== null) {
      console.log(`Found conflict in ${file}`);
  }

  // Replace with the bottom block
  content = content.replace(/<<<<<<< HEAD\n([\s\S]*?)=======\n([\s\S]*?)>>>>>>> [a-f0-9]+\n/g, '$2');
  
  fs.writeFileSync(file, content, 'utf8');
  console.log(`Fixed conflicts in ${file}`);
}
