#!/bin/bash
# Status check script — sends update via OpenClaw session
sleep 600  # 10 minutes

echo "=== 3DP CAD Skill Status Check $(date) ===" 
echo ""
echo "Files: $(find /home/halr9000/.openclaw/workspace/skills/3dp-cad/ -type f | wc -l)"
echo "Python lines: $(find /home/halr9000/.openclaw/workspace/skills/3dp-cad/ -name '*.py' -exec cat {} + | wc -l)"
echo "Tests: $(find /home/halr9000/.openclaw/workspace/skills/3dp-cad/tests/ -name 'test_*.py' | wc -l) test files"
echo "Git commits: $(cd /home/halr9000/.openclaw/workspace/skills/3dp-cad && git log --oneline | wc -l)"
echo "Packages: $(ls /home/halr9000/.openclaw/workspace/skills/3dp-cad/dist/ 2>/dev/null | wc -l) files in dist/"
echo ""
cat /home/halr9000/.openclaw/workspace/skills/3dp-cad/PROGRESS.md
