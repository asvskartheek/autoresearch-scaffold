// Render the dashboard's views in Node with a stub DOM, no browser needed.
//   node tests/render.js STATE.json [route] [DETAIL.json]   -> prints #main as plain text, flags problems, exit 1 if any
//   const {render} = require('./render'); render(state, 'hill/topology', {hill:{key:'topology',data:{...}}})
// DETAIL is {hill:{key,data}} | {detail:{...}} | {champ:{key,data}} merged into the app state `S` before drawing.
const fs = require('fs'), vm = require('vm'), path = require('path');
const STATIC = path.join(__dirname, '..', 'autoresearch', 'static');
const ORDER = ['lib', 'poster', 'goals', 'overview', 'champions', 'workbench', 'models', 'hills', 'slices', 'tasks', 'app'];

function render(state, route = 'overview', detail = {}) {
  const out = {nav: '', main: ''}, els = {};
  const el = id => els[id] || (els[id] = {set innerHTML(v) { out[id === '#nav' ? 'nav' : 'main'] = v; }, get innerHTML() { return out[id === '#nav' ? 'nav' : 'main']; }, style: {}, appendChild() {}, querySelectorAll: () => []});
  const ctx = {
    console, setInterval() {}, setTimeout, scrollTo() {}, addEventListener() {}, scrollY: 0, innerWidth: 1280,
    location: {hash: '#' + route}, fetch: () => new Promise(() => {}),
    document: {querySelector: el, querySelectorAll: () => [], createElement: () => ({style: {}, set innerHTML(v) {}}), addEventListener() {}, body: {appendChild() {}}, title: ''},
  };
  vm.createContext(ctx);
  const src = ORDER.map(f => fs.readFileSync(path.join(STATIC, f + '.js'), 'utf8')).join('\n');
  vm.runInContext(src + '\nthis.__S=S;this.__render=render;', ctx, {filename: 'dashboard'});
  Object.assign(ctx.__S, {state, ok: true}, detail);
  ctx.__render();
  return out.main;
}
const text = html => html.replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim();
function problems(html) {
  const t = text(html), bad = [];
  for (const re of [/\bundefined\b/, /\bNaN\b/, /\[object Object\]/, /\bnull\b/, /Infinity/]) if (re.test(t)) bad.push(`text contains ${re}`);
  if (/(?:^|>)\s*—\s*(?:<|$)/.test(html) && false) bad.push('bare dash');
  return bad;
}
module.exports = {render, text, problems};
if (require.main === module) {
  const [, , sf, route = 'overview', df] = process.argv;
  const html = render(JSON.parse(fs.readFileSync(sf, 'utf8')), route, df ? JSON.parse(fs.readFileSync(df, 'utf8')) : {});
  console.log(text(html));
  const bad = problems(html);
  if (bad.length) { console.error('PROBLEMS: ' + bad.join('; ')); process.exit(1); }
}
