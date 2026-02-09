#!/bin/bash
# test_vite_commands.sh
# Tests to verify Vite commands run without hanging

echo "🧪 Testing Non-Interactive Vite Commands"
echo "========================================"
echo ""

# Test 1: Using 'yes' command
echo "Test 1: Using 'yes' command prefix"
echo "Command: yes '' | npm create vite@latest test-app-1 -- --template react-ts"
echo "Expected: Should complete without hanging"
echo ""

timeout 30 bash -c "yes '' | npm create vite@latest test-app-1 -- --template react-ts" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 124 ]; then
    echo "❌ FAILED: Command timed out (still hanging)"
elif [ $EXIT_CODE -eq 0 ]; then
    echo "✅ PASSED: Command completed successfully"
    rm -rf test-app-1
else
    echo "⚠️  Command exited with code: $EXIT_CODE"
fi

echo ""
echo "========================================"
echo ""

# Test 2: Without 'yes' command (should hang)
echo "Test 2: Without 'yes' command (expected to hang)"
echo "Command: npm create vite@latest test-app-2 -- --template react-ts"
echo "Expected: Should timeout in 10 seconds"
echo ""

timeout 10 bash -c "npm create vite@latest test-app-2 -- --template react-ts" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 124 ]; then
    echo "✅ PASSED: Command hung as expected (timeout)"
elif [ $EXIT_CODE -eq 0 ]; then
    echo "⚠️  UNEXPECTED: Command completed (Vite may have changed)"
    rm -rf test-app-2
else
    echo "⚠️  Command exited with code: $EXIT_CODE"
fi

echo ""
echo "========================================"
echo "Test Summary:"
echo "- Use 'yes' command to auto-answer prompts"
echo "- Prefix: yes '' | <command>"
echo "- This sends empty string to all prompts"
echo "========================================"