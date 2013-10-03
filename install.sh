#!/usr/bin/env bash

SCRIPT_DIR=`dirname $0`
PATH_TO_KIT="${PWD}/${SCRIPT_DIR}"

SUCCESS=1
FILE=""
if test -n "$ZSH_VERSION"; then
  FILE=".zshrc"
elif test -n "$BASH_VERSION"; then
  FILE=".bashrc"
elif test -n "$KSH_VERSION"; then
  FILE=".kshrc"
elif test -n "$FCEDIT"; then
  FILE=".kshrc"
else
  echo "Add an alias for 'kk' to your shell .rc file, like so"
  echo "alias 'kk'='python $PATH_TO_KIT/kit.py'"
  SUCCESS=0
fi

if [[ ${SUCCESS} = 1 ]]; then
  sed -i '/^\s*alias.*python.*kit\.py.*$/d' ${HOME}/${FILE}
  echo "alias 'kk'='python $PATH_TO_KIT/kit.py'" >> ${HOME}/${FILE}
  alias 'kk'='python $PATH_TO_KIT/kit.py'

  echo "
Installed the kitchen sink pager as an alias in ${HOME}/${FILE} to 
${PATH_TO_KIT}

Note: If the location of this directory changes, update the alias or rerun this installer."
fi
