#!/usr/bin/env python
# -*- coding: latin-1 -*-


import curses
import itertools
import os
import sys
import time
import urlparse


import pygments
import pygments.formatters
from pygments.lexers import guess_lexer

def read_lines(stdscr):
  maxx = 0
  numlines = 0
  lines = []
  for line in sys.stdin:
    maxx = max(maxx, len(line))
    numlines += 1
    lines.append(line)

  maxy = numlines

  joined = ''.join(lines)

  # this is the second pass, and where the actual parsing of tokens should
  # probably happen. In addition, we should look at the tokens in each line and
  # maybe highlight specific ones? #www.yahoo.com


  all_tokens = []
  for index, line in enumerate(lines):
    col = 0
    try:
      stdscr.addstr(index, 0, line)

    except Exception, e:
      print e

    while line[col] == " ":
      col += 1

    tokens = line.split()
    for token in tokens:
      all_tokens.append({
        "text" : token.strip(),
        "line" : index,
        "col" : col
      })

      col += len(token) + 1

  return {
    "maxx": maxx,
    "maxy": maxy,
    "lines": lines,
    "joined" : joined,
    "tokens" : all_tokens
  }


"http://google.com"

"http://yahoo.com"

def do_syntax_coloring(ret, scr=None):
  lexer = guess_lexer(ret['joined'])
  output = pygments.highlight(ret['joined'], lexer, pygments.formatters.Terminal256Formatter())
  print output


def do_get_urls(ret, scr=None):
  tokens = ret['tokens']
  urls = []
  import re
  for token in tokens:
    match = re.search("^\W*(https?://[\w\.]*|www.[\w\.]*)", token['text'])
    if match:
      urls.append(match.group(1))

  print '\n'.join(urls)

  return True

def do_quit(ret, scr):
  return True

def main(stdscr):
  stdscr.erase()
  ret = read_lines(stdscr)

  # We're done with stdin,
  # now we want to read input from current terminal
  with open("/dev/tty") as f:
    os.dup2(f.fileno(), 0)

  y, x = stdscr.getmaxyx()

  stdscr.refresh()
  ch = -1


  pre_curses_hooks = {
    "q" : do_quit
  }
  post_curses_hooks = {
    "s" : do_syntax_coloring,
    "u" : do_get_urls
  }

  while True:
    ch = stdscr.getch()
    if ch != -1:
      key = str(unichr(ch))

    if key in pre_curses_hooks:
      ret = pre_curses_hooks[key](ret, stdscr)
      if ret:
        return ret

    if key in post_curses_hooks:
      def func():
        post_curses_hooks[key](ret)

      return func

  return func

if __name__ == "__main__":
  after = curses.wrapper(main)
  if hasattr(after, '__call__'):
    try:
      after()
    except Exception, e:
      raise e
