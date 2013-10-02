import curses
import itertools
import os
import sys
import time


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
  # maybe highlight specific ones?


  all_tokens = []
  for index, line in enumerate(lines):
    col = 0
    try:
      stdscr.addstr(index, 0, line)
      tokens = line.split()
      while line[col] == " ":
        col += 1

      for token in tokens:
        stdscr.addstr(index, col, token[0], curses.A_BOLD)

        all_tokens.push({
          "token" : token,
          "line" : index,
          "col" : col
        })

        col += len(token) + 1

    except:
      pass

  return {
    "maxx": maxx,
    "maxy": maxy,
    "lines": lines,
    "joined" : joined,
    "tokens" : all_tokens
  }



def do_syntax_coloring(ret):
  def func():
    lexer = guess_lexer(ret['joined'])
    output = pygments.highlight(ret['joined'], lexer, pygments.formatters.Terminal256Formatter())
    print output

  return func

def do_get_urls(ret):
  return

def do_quit(ret):
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
    "u" : do_get_urls,
    "q" : do_quit
  }
  post_curses_hooks = {
    "s" : do_syntax_coloring
  }

  while True:
    ch = stdscr.getch()
    if ch != -1:
      key = str(unichr(ch))

    if key in pre_curses_hooks:
      ret = pre_curses_hooks[key](ret)
      if ret:
        return ret

    if key in post_curses_hooks:
      ret = post_curses_hooks[key](ret)
      if ret:
        return ret

  return func

if __name__ == "__main__":
  after = curses.wrapper(main)
  if hasattr(after, '__call__'):
    try:
      after()
    except:
      pass
