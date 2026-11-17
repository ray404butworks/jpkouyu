/* 前端审计工具仅在开发时运行；Acorn 从调用者指定的目录加载，不随运行时分发。 */
const fs = require('node:fs');
const path = require('node:path');
const parserPath = process.argv[2];
if (!parserPath) throw new Error('请传入审计环境中 Acorn 的绝对路径。');
const acorn = require(path.resolve(parserPath));
const root = path.resolve(__dirname, '..');
const files = ['assets/workbench/app.js', 'assets/workbench/daily-quotes.js', 'scripts/test_daily_quotes.cjs', 'scripts/audit_frontend.cjs'];
const result = {functions: 0, missing_chinese_comments: [], dangerous_sinks: []};

/* 递归检查函数紧邻中文注释，并列出需要逐项追踪数据来源的 HTML 渲染点。 */
function inspect(node, code, comments, file) {
  if (!node || typeof node !== 'object') return;
  if (/Function/.test(node.type)) {
    result.functions++;
    const documented = comments.some(/* 只认可紧邻该函数且包含中文的注释。 */ comment => comment.end <= node.start && code.slice(comment.end, node.start).trim() === '' && /[\u4e00-\u9fff]/.test(comment.value));
    if (!documented) result.missing_chinese_comments.push(`${file}:${node.loc.start.line}`);
  }
  const target = node.type === 'AssignmentExpression' ? node.left : node.type === 'CallExpression' ? node.callee : null;
  if (target?.type === 'MemberExpression' && ['innerHTML', 'outerHTML', 'insertAdjacentHTML', 'write', 'writeln'].includes(target.property?.name)) {
    result.dangerous_sinks.push({file, line: node.loc.start.line, property: target.property.name, status: 'requires data-flow review'});
  }
  for (const [key, value] of Object.entries(node)) {
    if (['loc', 'start', 'end'].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(/* 遍历语法树列表中的每个子节点。 */ child => inspect(child, code, comments, file));
    else inspect(value, code, comments, file);
  }
}

for (const file of files) {
  const code = fs.readFileSync(path.join(root, file), 'utf8');
  const comments = [];
  const tree = acorn.parse(code, {ecmaVersion: 'latest', locations: true, onComment: comments});
  inspect(tree, code, comments, file);
}
console.log(JSON.stringify(result, null, 2));
if (result.missing_chinese_comments.length) process.exitCode = 1;
