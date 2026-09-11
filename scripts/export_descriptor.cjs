const fs = require('fs');
const data = require('../.dev/descriptor.cjs');
fs.writeFileSync('data/descriptor.json', JSON.stringify({fields: data.DESCRIPTOR_FIELDS, tags: data.LAUNCHER_TAGS}, null, 2) + '\n');
