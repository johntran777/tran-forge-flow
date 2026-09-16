#!/usr/bin/env bash
# Instantiates the Tran Forge bowling-kata demo into a disposable working copy.
#
# The example/ folder ships git-less (it lives inside the ai-agent-flow repo; a nested .git would
# confuse both repos). This script copies it out, installs the flow into .claude/, resolves the
# Java 25 + modern Maven toolchain into tran-forge.config.md, and inits a fresh git repo.
#
# Usage: ./setup.sh [target-dir]     (default: ../example-run, gitignored by tran-forge-flow)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FLOW_DIR="$(dirname "$SCRIPT_DIR")"                       # tran-forge-flow/
TARGET="${1:-$FLOW_DIR/example-run}"

if [[ -e "$TARGET" && -n "$(ls -A "$TARGET" 2>/dev/null)" ]]; then
  echo "ERROR: target $TARGET already exists and is not empty. Remove it or pass another path." >&2
  exit 1
fi

# --- 1. Copy the kata template (everything except this script) --------------------------------
mkdir -p "$TARGET"
(cd "$SCRIPT_DIR" && find . -type f ! -name 'setup.sh' -print0 | while IFS= read -r -d '' f; do
  mkdir -p "$TARGET/$(dirname "$f")"
  cp "$f" "$TARGET/$f"
done)

# --- 2. Install the flow into .claude/ ---------------------------------------------------------
mkdir -p "$TARGET/.claude"
cp -R "$FLOW_DIR/agents" "$TARGET/.claude/agents"
cp -R "$FLOW_DIR/skills" "$TARGET/.claude/skills"

if [[ ! -f "$TARGET/.claude/settings.json" ]]; then
  cat > "$TARGET/.claude/settings.json" <<'JSON'
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
JSON
fi

# --- 3. Resolve the toolchain (Java 25 + Maven >= 3.6.3) and bake it into the config ----------
is_java25() {  # macOS java_home can "succeed" with an ancient JDK — trust only a version probe
  [[ -x "$1/bin/java" ]] && "$1/bin/java" -version 2>&1 | grep -q 'version "25'
}

find_java25() {
  local p
  p="$(/usr/libexec/java_home -v 25 2>/dev/null || true)"
  if [[ -n "$p" ]] && is_java25 "$p"; then echo "$p"; return; fi
  for p in /usr/local/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home \
           /opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home \
           /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \
           /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home; do
    is_java25 "$p" && { echo "$p"; return; }
  done
  return 1
}

find_mvn() {
  for m in /usr/local/opt/maven/bin/mvn /opt/homebrew/opt/maven/bin/mvn "$(command -v mvn || true)"; do
    [[ -n "$m" && -x "$m" ]] || continue
    v="$(JAVA_HOME="$JAVA25" MAVEN_OPTS= "$m" -version 2>/dev/null | sed -n 's/^Apache Maven \([0-9.]*\).*/\1/p')"
    [[ -n "$v" ]] || continue
    case "$v" in 3.[0-5].*) continue ;; esac   # need >= 3.6.3 for Spring Boot 4
    echo "$m"; return
  done
  return 1
}

JAVA25="$(find_java25)" || { echo "ERROR: no Java 25 JDK found (brew install openjdk@25)." >&2; exit 1; }
MVN_BIN="$(find_mvn)"   || { echo "ERROR: no Maven >= 3.6.3 found (brew install maven)." >&2; exit 1; }

# MAVEN_OPTS is cleared in the baked command: inherited profiles may carry JDK-7-era flags
# (e.g. -XX:MaxPermSize) that Java 25 refuses to start with.
MVN_CMD="MAVEN_OPTS= JAVA_HOME=\"$JAVA25\" $MVN_BIN"
sed -i '' "s|{{MVN}}|$MVN_CMD|g" "$TARGET/tran-forge.config.md" 2>/dev/null \
  || sed -i "s|{{MVN}}|$MVN_CMD|g" "$TARGET/tran-forge.config.md"

# --- 4. Fresh git repo -------------------------------------------------------------------------
cd "$TARGET"
git init -b main -q
git add -A
git commit -q -m "Bowling kata scaffold (Tran Forge demo)"

# --- 5. Sanity: the toolchain must be green on the virgin kata ---------------------------------
echo "Running toolchain smoke (mvn -q test)..."
if eval "$MVN_CMD -q test" >/dev/null 2>&1; then
  echo "Toolchain smoke: GREEN"
else
  echo "WARNING: mvn test failed in $TARGET — run it manually to inspect." >&2
fi

cat <<EOF

Tran Forge demo ready at: $TARGET

Next steps:
  cd $TARGET
  claude
  /tran-forge          # first cycle should target Feature 1 (open frames)

The pipeline pauses twice: once to approve the Gherkin spec (before any code is written), and once to
sign off the manual-test report (before anything merges back). It then asks whether to keep the
requirement + .feature artifacts.

Phase 4 runs two Codex reviews (security/OWASP + performance) at gpt-5.6-sol/xhigh. Without the codex CLI
on PATH the flow reports that phase as SKIPPED — set codex_enabled: false in tran-forge.config.md to
skip it deliberately instead.
EOF
