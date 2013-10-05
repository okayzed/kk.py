#!/usr/bin/env python
# -*- coding: latin-1 -*-

# {{{ about
# The kitchen sink is a smarter pager. It lets you operate on any output and quickly take action

# things the kitchen sink could potentially do:

# DONE
# x locate (and open) files in the output
# x open urls from the output
# x add syntax highlighting to any output
# x add syntax highlighting to git diffs
# x open the output in an external editor
# x locate urls in the output
# x search next word
# x search prev function
# x create a stack for jumping between opened buffers
# x pipe buffer into a command and re-open pager on new output

# TODO
# o compare two different outputs (do ad-hoc diffs)
# o session manager for past contents
#   o yank the output into a 'buffer'
# o sum a column
# o sum a row
# o have a mode to dump an old session from kit to stdout

# }}}

# {{{ imports
import curses
import itertools
import os
import re
import subprocess
import sys
import time
import urlparse
import urwid

import pygments
import pygments.formatters
from urwidpygments import UrwidFormatter
from pygments.lexers import guess_lexer
# }}}

# {{{ util
def add_vim_movement():
  updatedMappings = {
    'k':        'cursor up',
    'j':      'cursor down',
    'h':      'cursor left',
    'l':     'cursor right',
    'ctrl u':   'cursor page up',
    'ctrl d': 'cursor page down'
  }

  for key in updatedMappings:
    urwid.command_map[key] = updatedMappings[key]


debugfile = open(__name__ + ".debug", "w")
def debug(*args):
  print >> debugfile, " ".join([str(i) for i in args])

# }}}

# {{{ input
def tokenize(lines):
  # http://redd.it (example URL)
  all_tokens = []
  for index, line in enumerate(lines):
    col = 0

    while col < len(line) and line[col] == " ":
      col += 1

    tokens = line.split()
    for token in tokens:
      all_tokens.append({
        "text" : token,
        "line" : index,
        "col" : col
      })

      col += len(token) + 1
  return all_tokens

def read_lines(in_lines=None):
  maxx = 0
  numlines = 0
  content = False
  debug("LIENS", in_lines)

  if not in_lines:
    in_lines = list(sys.stdin.readlines())

  lines = []
  for line in in_lines:
    maxx = max(maxx, len(line))
    numlines += 1
    line = line.replace('[\x01-\x1F\x7F]', '')
    lines.append(line)
    if not content and line.strip() != "":
      content = True

  maxy = numlines

  joined = ''.join(lines)

  # this is the second pass, and where the actual parsing of tokens should
  # probably happen. In addition, we should look at the tokens in each line and
  # maybe highlight specific ones? #www.yahoo.com

  all_tokens = tokenize(lines)

  return {
    "maxx": maxx,
    "maxy": maxy,
    "lines": lines,
    "joined" : joined,
    "tokens" : all_tokens,
    "has_content" : content
  }


"http://google.com/the/first/one"

"http://yahoo.com/?asecond=eht"

# }}}

# {{{ external editor
# http://stackoverflow.com/questions/2576956/getting-data-from-external-program
def _get_content(editor, initial=""):
    from subprocess import call
    from tempfile import NamedTemporaryFile

    tfName = None
    # Create the initial temporary file.
    with NamedTemporaryFile(delete=False) as tf:
        tfName = tf.name
        debug("opening file in editor:" + str(tfName))
        tf.write(initial)

    # Fire up the editor.
    code = call([editor, tfName])
    if code != 0:
        return None # Editor died or was killed.

    # Get the modified content.
    with open(tfName, "r") as f:
        result = f.readlines()
        os.remove(tfName)
        return result
# }}}

# {{{ TextBox widget

class TextBox(urwid.ListBox):
  def __init__(self, *args, **kwargs):
    self.last_focused_lines = []
    return super(TextBox, self).__init__(*args, **kwargs)

  def render(self, size, focus=False):
    self.highlight_middle(size, focus)
    return super(TextBox, self).render(size, focus)

  def highlight_middle(self, size, focus):
    return

    vis = self.calculate_visible(size, focus)
    if self.last_focused_lines:
      for line in self.last_focused_lines:
        line.set_text((prev_style, line.get_text()[0]))

    top_trimmed_rows = vis[1][1]
    bot_trimmed_rows = vis[2][1]


    def highlight_line(line_no):
      try:
        focus_widget = self.body[line_no]
        if focus_widget:
          text = focus_widget.get_text()[0]
          focus_widget.prev_style = focus_widget.get_text()[0]
          focus_widget.set_text(('highlight', text))
          self.last_focused_lines.append(focus_widget)
      except:
        return

    # Figure out what the middle line is, so we can highlight it
    start_index = 0
    top_visible = None
    bottom_visible = None
    end_index = None
    if top_trimmed_rows:
      top_visible = top_trimmed_rows[-1]
      start_index = top_visible[1]
      end_index = size[1] + start_index

    if bot_trimmed_rows:
      bottom_visible = bot_trimmed_rows[-1]
      end_index = bottom_visible[1]
      if not start_index:
        start_index = end_index - size[1]

    debug(start_index, end_index)

    end_index = end_index or size[1]
    middle = abs(end_index - start_index) / 2 + start_index
    highlight_line(middle)



# }}}
# {{{ overlay widget
class OverlayStack(urwid.WidgetPlaceholder):
  def __init__(self, *args, **kwargs):
    super(OverlayStack, self).__init__(*args, **kwargs)
    self.overlay_opened = False

  def open_overlay(self, widget, modal_keys=None, **options):
    global _key_hooks
    if not modal_keys:
      modal_keys = {}

    modal_keys.update({ "q" : CURSES_HOOKS['q'], "esc" : CURSES_HOOKS['esc'], "backspace" : CURSES_HOOKS['esc'] })
    # we should install these modal keys
    _key_hooks = modal_keys

    if not self.overlay_opened:
      defaults = {
        "align" : "center",
        "width" : ("relative", 50),
        "valign" : "middle",
        "height" : ("relative", 50)
      }
      defaults.update(options)

      overlay = urwid.Overlay(
        widget,
        self.original_widget,
        **defaults
      )

      self.overlay_parent = self.original_widget
      self.overlay = overlay

      self.original_widget = self.overlay

    self.overlay_opened = True

  def close_overlay(self, ret=None, widget=None):
    global _key_hooks
    self.original_widget = self.overlay_parent
    self.overlay_opened = False
    _key_hooks = CURSES_HOOKS

# }}}

# {{{ character handlers

syntax_colored = False
previous_widget = None

def get_focus_index(widget, rows):
  offset, inset = widget.get_focus_offset_inset((1, rows))
  focus_widget, focus_index = widget.get_focus()

  return focus_index, offset

def readjust_display(kv, listbox, focused_index):

  index, offset = focused_index
  if kv.last_search_token:
    text, attr = kv.last_search_token.get_text()
    kv.last_search_token.set_text((None, text))
    kv.last_search_token = listbox.body[kv.last_search_index]
    new_text, attr = kv.last_search_token.get_text()
    kv.last_search_token.set_text(('highlight', new_text))

  listbox.set_focus(index)
  listbox.set_focus_valign(('fixed top', offset))


def do_syntax_coloring(kv, ret, widget):
  global previous_widget, syntax_colored
  walker = urwid.SimpleListWalker([])

  if previous_widget:
    original_text = widget.original_widget
    focused_index = get_focus_index(original_text, ret['maxy'])
    widget.original_widget = previous_widget
    previous_widget = original_text

    debug("SYNTAX COLORING PREV WIDGET")

    syntax_colored = not syntax_colored
    readjust_display(kv, widget.original_widget, focused_index)
    return


  debug("INITIALIZING SYNTAX COLORED WIDGET")
  # one time setup
  previous_widget = widget.original_widget
  listbox = TextBox(walker)
  widget.original_widget = listbox
  syntax_colored = True
  focused_index = get_focus_index(previous_widget, ret['maxy'])

  formatter = UrwidFormatter()
  # special case for git diffs
  def handle_token(token, formatted_line, newline, diff=False):
    text = token[1]
    debug("HANDLING TOKEN", newline, diff, repr(text))
    if not text:
      return newline

    if newline and diff and False:
      if text[0] == '+':
        debug("DIFF ADD")
        formatted_line.append(('diff_add', '+'))
        text = token[1][1:]
        token = (token[0], text)
      elif text[0] == '-':
        formatted_line.append(('diff_del', '-'))
        text = token[1][1:]
        token = (token[0], text)
        debug("DIFF DEL")

    if text.find('\n') >= 0:
      split_line = text
      while split_line:
        n = split_line.find('\n')
        if n >= 0:
          newline = True
          last_word = split_line[:n]
          split_line = split_line[n+1:]
          formatted_line.append('')
          walker.append(urwid.Text(list(formatted_line)))
          del formatted_line[:]
        else:
          formatted_line.append((token[0], split_line))
          break
    else:
      formatted_line.append(token)
      newline = False

    return newline
    # end of handle_token function


  def add_lines_to_walker(lines, walker, fname=None, diff=False):
    if len(lines):
      output = "".join(lines)
      lexer = guess_lexer(output)
      try:
        if fname:
          lexer = pygments.lexers.guess_lexer_for_filename(fname, output)
      except:
        pass

      tokens = lexer.get_tokens(output)

      # Build the syntax output up line by line, so that it can be highlighted
      # one line at a time
      formatted_tokens = list(formatter.formatgenerator(tokens))
      formatted_line = []
      newline = False

      for token in formatted_tokens:
        newline = handle_token(token, formatted_line, newline, diff)

      formatted_line.append('')

      if formatted_line:
        walker.append(urwid.Text(list(formatted_line)))



  if ret['joined'].find("diff --git") >= 0:
    walker[:] = [ ]
    wlines = []
    lexer = None
    fname = None

    for line in ret['lines']:
      if line.startswith("diff --git"):
        output = "".join(wlines)

        add_lines_to_walker(wlines, walker, fname, diff=True)

        # next output
        fname = line.split().pop()
        wlines = [ ]

      wlines.append(line)

    add_lines_to_walker(wlines, walker, fname, diff=True)
  else:
    lines = ret['lines']
    add_lines_to_walker(lines, walker, None)

  # an anchor blank element for easily scrolling to bottom of this text view
  walker.append(urwid.Text(''))
  readjust_display(kv, widget.original_widget, focused_index)

def overlay_menu(widget, title, items, cb):
  def button(text, value):
    def button_pressed(but):
      debug("BUTTON PRESSED", title, text)
      cb(text)

    button = urwid.Button(text[:40], on_press=button_pressed)

    return button

  walker = urwid.SimpleListWalker([button(token, token) for token in items])
  walker.insert(0, urwid.Text(title))
  listbox = urwid.ListBox(walker)
  url_window = urwid.LineBox(listbox)
  widget.open_overlay(url_window)

def is_git_like(obj):
  with open(os.devnull, "w") as fnull:
    ret = subprocess.call(['git', 'show', obj], stdout=fnull, stderr=fnull)

  return ret == 0

def do_get_git_objects(kv, ret, widget):
  import re
  tokens = ret['tokens']
  files = []
  visited = {}
  for token in tokens:
    text = token['text']
    if not text in visited:
      visited[text] = True
      if re.search('^\w*\d*\w\d(\d|\w)+$', text):
        debug("GIT HASH?", text)
        if is_git_like(text):
          files.append(text[:10])

  if not len(files):
    files.append("No git objects found in document")

  def func(response):
    contents = subprocess.check_output(['git', 'show', response])
    lines = [contents]
    widget.close_overlay()
    previous_widget = None
    syntax_colored = False
    kv.read_and_display(lines)

  overlay_menu(widget, "Choose a git object to open", files, func)



def do_get_files(kv, ret, widget):
  tokens = ret['tokens']
  files = []
  visited = {}
  for token in tokens:
    text = token['text']
    while text:
      if not text in visited:
        visited[text] = True
        if os.path.isfile(text):
          files.append(text)
          break

      text_dirs = text.split('/')
      text_dirs.pop(0)
      text = '/'.join(text_dirs)

  if not len(files):
    files.append("No files found in document")

  def func(response):
    try:
      with open(response, "r") as f:
        contents = list(f.readlines())
        debug("READ FILE", contents)
        widget.close_overlay()
        previous_widget = None
        syntax_colored = False
        kv.read_and_display(contents)
    except Exception, e:
      debug("EXCEPTION", e)

  overlay_menu(widget, "Choose a file to open", files, func)

def do_get_urls(kv, ret, widget=None):
  tokens = ret['tokens']

  urls = []
  import re
  for token in tokens:
    match = re.search("^\W*(https?://[\w\./]*|www.[\w\./\?&\.]*)", token['text'])
    if match:
      urls.append(match.group(1))


  if not len(urls):
    urls.append("No URLS found in document")

  def func(response):
    if not response.startswith('http'):
      response = "http://%s" % response
    subprocess.Popen(["/usr/bin/xdg-open", response])
    widget.close_overlay()

  overlay_menu(widget, "Choose a URL to open", urls, func)

def do_print(kv, ret, scr):
  def func():
    print ret['joined']

  kv.after_urwid.append(func)
  raise urwid.ExitMainLoop()

def do_interactive_sed(kv, ret, scr=None):
  pass

def do_close_overlay_or_quit(kv, ret, widget):
  if  widget.overlay_opened:
    debug("CLOSING OVERLAY")
    widget.close_overlay()
  else:
    debug("QUITTING")
    raise urwid.ExitMainLoop()

def do_quit(kv, ret, scr):
  raise urwid.ExitMainLoop()

def do_pop_stack(kv, ret, scr):
  kv.restore_last_display()

def do_edit_text(kv, ret, widget):
  global previous_widget, syntax_colored

  lines = _get_content(os.environ["EDITOR"], ret["joined"])
  previous_widget = None
  syntax_colored = False
  display_lines(lines, widget)
  ret['lines'] = lines
  ret['joined'] = ''.join(lines)
  ret['tokens'] = tokenize(lines)

def do_yank_text(kv, ret, widget):
  kv.display_status_msg("yanking buffers is still unimplemented")

def do_next_search(kv, ret, widget):
  kv.find_and_focus()

def do_prev_search(kv, ret, widget):
  kv.find_and_focus(reverse=True)

def do_scroll_top(kv, ret, widget):
  widget.original_widget.set_focus_valign('top')
  widget.original_widget.set_focus(0)

def do_scroll_bottom(kv, ret, widget):
  widget.original_widget.set_focus_valign("bottom")
  debug(widget.original_widget.body[-1])
  widget.original_widget.set_focus(len(widget.original_widget.body) + 1)

def do_general(kv, ret, widget):
  debug("Entering general mode")
  setup_general_hooks()

def do_pipe_prompt(kv, ret, widget):
  debug("ENTERING PIPE MODE")
  kv.open_command_line('!')
def do_search_prompt(kv, ret, widget):
  debug("ENTERING SEARCH MODE")
  kv.open_command_line('/')

def do_command_prompt(kv, ret, widget):
  debug("ENTERING COMMAND MODE")
  kv.open_command_line(':')

def handle_command(prompt, command):
  debug("Handling command", prompt, command)
  if prompt == '/':
    kv.find_and_focus(command)
  elif prompt == ':':
    kv.display_status_msg('Sorry, command mode is not yet implemented')
  elif prompt == '!':
    kv.pipe_and_display(command)
  else:
    kv.display_status_msg('Sorry, %s mode is not yet implemented' % (prompt))

def do_command_entered(kv, ret, widget):
  if kv.in_command_prompt:
    cmd, opts = kv.prompt.get_text()
    kv.prompt.set_edit_text('')
    handle_command(kv.prompt_mode, cmd)

  kv.close_command_line()

def do_open_help(kv, ret, widget):
  listitems = []

  helps = []
  shortcuts = []
  for item in sorted(_key_hooks.keys()):
    msg = _key_hooks[item].get('help')
    if msg:
      shortcut = urwid.Text([ " ", ('highlight', item[:9])])
      shortcut.align = "left"
      help_msg = urwid.Text(msg + "  ")
      help_msg.align = "right"

      columns = urwid.Columns([ ("fixed", 10, shortcut), ("weight", 1, help_msg)])
      listitems.append(columns)

  listbox = TextBox(listitems)
  widget.open_overlay(urwid.LineBox(listbox),
    width=("relative", 80), height=("relative", 80))

CURSES_HOOKS = {
  ":" : {
    "fn" : do_command_prompt,
    "help" : "Enter command mode",
  },
  "/" : {
    "fn" : do_search_prompt,
    "help" : "Enter interactive search"
  },
  "!" : {
    "fn" : do_pipe_prompt,
    "help" : "Pipe current buffer through an external command"
  },
  "q" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "Quit kit / Close current overlay"
  },
  "p" : {
    "fn" : do_print,
    "help" : "Print window to stdout and quit"
  },
  "s" : {
    "fn" : do_syntax_coloring,
    "help" : "turn on syntax highlights"
  },
  "e" : {
    "fn" : do_edit_text,
    "help" : "open the current text in $EDITOR"
  },
  "g" : {
    "fn" : do_general,
    "help" : "enter general mode"
  },
  "G" : {
    "fn" : do_scroll_bottom,
    "help" : ""
  },
  "n" : {
    "fn" : do_next_search,
    "help" : ""
  },
  "N" : {
    "fn" : do_prev_search,
    "help" : ""
  },
  "y" : {
    "fn" : do_yank_text,
    "help" : "save the current kit output for later use"
  },
  "?" : {
    "fn" : do_open_help,
    "help" : "show this screen"
  },
  "esc" : {
    "fn" : do_close_overlay_or_quit,
    "help" : ""
  },
  "enter" : {
    "fn" : do_command_entered,
    "help" : ""
  },
  "f" : {
    "fn" : do_get_files,
    "help" : "list the files in current buffer"
  },
  "u" : {
    "fn" : do_get_urls,
    "help" : "list the URLs in the current buffer"
  },
  "o" : {
    "fn" : do_get_git_objects,
    "help" : "list the git objects in the current buffer"
  },
  "backspace" : {
    "fn" : do_pop_stack,
    "help" : "Visit previously opened buffer"
  }
}

GENERAL_HOOKS = {
  "?" : {
    "fn" : do_open_help,
    "help" : "Show this screen"
  },
  "q" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "Close this overlay"
  },
  "g" : {
    "fn" : do_scroll_top,
    "help" : "Scroll to top of content"
  },
}

for hook in GENERAL_HOOKS:
  def build_replacement():
    obj = GENERAL_HOOKS[hook]

    def replacement(*args, **kwargs):
      global _key_hooks
      debug("CALLING REPLACEMENT FUNCTION", obj)
      obj['oldfn'](*args, **kwargs)
      _key_hooks = CURSES_HOOKS

    obj['oldfn'] = obj['fn']
    obj['fn'] = replacement

  build_replacement()


def setup_general_hooks():
  global _key_hooks

  debug("USING GENERAL HOOKS")
  _key_hooks = GENERAL_HOOKS


# }}}

# {{{ display input
palette = [
  ('highlight', 'white', 'dark gray'),
  ('banner', 'black', 'white'),
  ('diff_add', 'black', 'light green'),
  ('diff_del', 'black', 'light red'),
  ('streak', 'black', 'dark red'),
  ('bg', 'black', 'dark blue'),
]


def display_lines(lines, widget):
  wlist = []
  for line in lines:
    col = 0
    stripped = line.lstrip()
    col = len(line) - len(stripped)

    wlist.append(urwid.Text(line.rstrip()))

  walker = urwid.SimpleListWalker(wlist)
  text = TextBox(walker)
  widget.original_widget = text

# }}}

# {{{ main viewer class


_key_hooks = CURSES_HOOKS
class Viewer(object):

  def __init__(self, *args, **kwargs):
    self.after_urwid = []
    self.in_command_prompt = False
    self.prompt_mode = ""
    self.last_search = ""
    self.stack = []
    self.last_search_index = 0
    self.last_search_token = None
    self.clear_edit_text = False

  def run(self, stdscr):
    ret = read_lines(None)
    self.ret = ret

    # We're done with stdin,
    # now we want to read input from current terminal
    with open("/dev/tty") as f:
      os.dup2(f.fileno(), 0)

    def handle_input(keys, raw):
      global _key_hooks
      unhandled = []
      debug("HANDLING INPUT", keys)

      was_general = False
      # always switch back
      if _key_hooks == GENERAL_HOOKS:
        was_general = True


      if self.clear_edit_text:
        self.prompt.set_edit_text("")
        self.prompt.set_caption("")
        self.clear_edit_text = False

      for key in keys:
        if not unhandle_input(key):
          unhandled.append(key)

      if was_general:
        _key_hooks = CURSES_HOOKS
        return []


      return unhandled

    def unhandle_input(key):
      if self.in_command_prompt:
        if key == 'enter':
          do_command_entered(kv, self.ret, widget)
          return True

        if key == 'esc':
          self.close_command_line()
          return True

        return

      if key in _key_hooks.keys():
        debug("KEY ", key, "PRESSED")
        _key_hooks[key]['fn'](self, self.ret, widget)
        return True

    add_vim_movement()
    widget = OverlayStack(urwid.Text(""))

    self.prompt = urwid.Edit()
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(self.prompt_mode)), ("weight", 1, self.prompt)])
    self.command_line = urwid.WidgetPlaceholder(prompt_cols)
    self.window = widget

    self.panes = urwid.Frame(widget, footer=self.command_line)
    display_lines(ret["lines"], widget)

    self.loop = urwid.MainLoop(self.panes, palette, unhandled_input=unhandle_input, input_filter=handle_input)

    self.display_status_msg(('banner', "Welcome to the qitchen sink pager. Press '?' for keybindings"))
    if ret['has_content']:
      self.loop.run()

  def repaint_screen(self):
    self.loop.draw_screen()

  def open_command_line(self, mode=':'):
    self.prompt_mode = mode
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(self.prompt_mode)), ("weight", 1, self.prompt)])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = True
    self.panes.set_focus('footer')
    self.prompt.set_edit_text("")

  def close_command_line(self, mode=':'):
    self.prompt.set_edit_text("")
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(" ")), ("weight", 1, self.prompt)])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = False
    self.panes.set_focus('body')


  def read_and_display(self, lines):
    global previous_widget
    previous_widget = None
    self.stack.append(self.ret)
    self.ret = read_lines(lines)
    display_lines(lines, self.window)

  def restore_last_display(self):
    global previous_widget
    previous_widget = None
    if self.stack:
      self.ret = self.stack.pop()
      display_lines(self.ret['lines'], self.window)

  def pipe_and_display(self, command):
    import shlex
    data_in = self.ret['joined']
    args = shlex.split(command)
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write(data_in)

    stdout = p.communicate()[0]

    kv.read_and_display([stdout])



  def find_and_focus(self, word=None, reverse=False):
    start_index = 0
    focused_widget, focused_index = self.window.original_widget.get_focus()
    start_index = focused_index

    if not word:
      word = self.last_search

    self.last_search = word

    tokens = self.window.original_widget.body
    def find_word(tokens, start_index):
      found = False

      if reverse:
        tokens = tokens[:start_index-1]
      else:
        tokens = tokens[start_index:]

      if self.last_search_token:
        text, opts = self.last_search_token.get_text()
        self.last_search_token.set_text((None, text))

      enum_tokens = enumerate(tokens)
      if reverse:
        enum_tokens = list(reversed(list(enumerate(tokens))))

      word_re = re.compile(word)
      for index, tok in enum_tokens:
        text, opts = tok.get_text()
        if word_re.search(text):
          debug("FOUND WORD", word, "IN", text)
          self.window.original_widget.set_focus_valign('middle')

          self.last_search_index = start_index + index
          if reverse:
            self.last_search_index = index
          self.last_search_token = tok

          found = True
          break

      if found:
        found_text = self.last_search_token.get_text()[0]
        debug("INDEX OF", found_text, "IS", self.last_search_index)
        self.window.original_widget.set_focus(self.last_search_index)
        self.last_search_token.set_text(('highlight', text))
      return found

    found = find_word(tokens, start_index + 1)
    if not found:
      kv.display_status_msg("Pattern not found. Wrapping")
      found = find_word(tokens, 0)

      if not found:
        kv.display_status_msg("Pattern not found  (Press RETURN)")


  def display_status_msg(self, msg):
    if type(msg) is str:
      msg = ('highlight', msg)
    self.prompt.set_caption(msg)
    self.prompt.set_edit_text("")
    self.clear_edit_text = True

if __name__ == "__main__":
  kv = Viewer()
  curses.wrapper(kv.run)
  for after in kv.after_urwid:
    if hasattr(after, '__call__'):
      try:
        after()
      except Exception, e:
        raise e
# }}}
