with open('ui/static/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    # Check for unmatched parentheses
    if line.count('(') != line.count(')'):
        if '(' in line or ')' in line:
            print(f'Line {i+1}: Unmatched parens: {line[:100]}')
    # Check for unmatched braces
    if line.count('{') != line.count('}'):
        if '{' in line or '}' in line:
            print(f'Line {i+1}: Unmatched braces: {line[:100]}')
    # Check for template literal issues
    backticks = line.count('\`')
    if backticks % 2 != 0:
        print(f'Line {i+1}: Odd backticks: {line[:100]}')

print('Done checking')