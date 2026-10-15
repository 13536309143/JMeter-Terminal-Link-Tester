#!/usr/bin/env bash
# Source this file to use the project-local Java and JMeter.
if [ -n "${BASH_VERSION:-}" ]; then
  JMETER_ENV_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  JMETER_ENV_FILE="${(%):-%x}"
else
  echo "Please source scripts/env.sh from bash or zsh" >&2
  return 1
fi
JMETER_PROJECT_DIR="$(cd "$(dirname "$JMETER_ENV_FILE")/.." && pwd)"
unset JMETER_ENV_FILE
export JMETER_PROJECT_DIR
export JAVA_HOME="$JMETER_PROJECT_DIR/runtime/jdk/Contents/Home"
export JMETER_HOME="$JMETER_PROJECT_DIR/runtime/apache-jmeter-5.6.3"
export JMETER_LANGUAGE="${JMETER_LANGUAGE:--Duser.language=zh -Duser.region=CN}"
export PATH="$JAVA_HOME/bin:$JMETER_HOME/bin:$PATH"
