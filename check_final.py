with open('ui/static/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Check for Lucide initialization calls
init_calls = content.count('initLucideIcons()')
print(f'initLucideIcons() calls: {init_calls}')

# Check for Lucide icon usage - look for data-lucide attributes
import re
lucide_icons = re.findall(r'data-lucide=["\']([^"\']+)["\']', content)
print(f'Lucide icons found: {len(lucide_icons)}')
icon_types = set(lucide_icons)
print(f'Unique icon types: {len(icon_types)} - {sorted(icon_types)}')

# Check for any remaining emoji using a simpler approach
# Check for common emoji codepoints as literal strings
emoji_chars = [
    '\U0001F474',  # old man
    '\U0001F48A',  # pill
    '\U0001F504',  # refresh
    '\u26A0',      # warning
    '\u2705',      # check mark
    '\U0001F4CA',  # chart
    '\U0001F3EA',  # store
    '\U0001F468\u200D\u2695\uFE0F',  # doctor
    '\u2B50',      # star
    '\U0001F4C8',  # chart up
    '\U0001F4C9',  # chart down
    '\U0001F534',  # red circle
    '\U0001F7E1',  # yellow circle
    '\u26A0',      # warning
    '\U0001F3EA',  # store
    '\U0001F468\u200D\u2695\uFE0F',  # doctor
    '\U00002B50',  # star
]

found_any = False
for emoji in emoji_chars:
    if emoji in content:
        idx = content.find(emoji)
        line_num = content[:idx].count('\n') + 1
        print(f'Found emoji at line {line_num}: {emoji!r}')
        found_any = True

if not found_any:
    print('No emoji characters found - clean!')