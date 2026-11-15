import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
const result = await build({entryPoints:['renmon/static/app.js'], bundle:true, format:'iife', target:['safari15','edge100'], write:false, legalComments:'none'});
const content = result.outputFiles[0].text;
const path='renmon/ui.bundle.js';
if (process.argv.includes('--check')) {
  if (await readFile(path,'utf8') !== content) throw Error('UI bundle is stale. Run npm run build.');
} else await writeFile(path, content);
