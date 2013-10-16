#!/usr/bin/env python
# -*- coding: latin-1 -*-

# {{{ about
# The kitchen sink is a smarter pager. It lets you operate on any output and quickly take action

# DONE
# x locate (and open) files in the output
# x open urls from the output
# x preliminary terminal color support
# x add syntax highlighting to any output
# x add syntax highlighting to git diffs
# x open the output in an external editor
# x locate urls in the output
# x search next word
# x search prev function
# x create a stack for jumping between opened buffers
# x pipe buffer into a command and re-open pager on new output
# x yank the output into xsel buffer
# x compare two different outputs (current buffer and xsel sound good to me)
# GENERAL:
# x speed up the log parsing for git commits (make this more asynchronous)
# BUGS
# fix partial syntax highlighting that can happen when switching during reading

# TODO

# o MATH
# o sum a column
# o sum a row
# o generate a histogram
# o calculate the big stats (avg, mean, etc)

# COLORS / WEB DEV
# o highlight hex colors
# o print a hex color in multiple formats?
# o grab all hex colors

# BUGS:

# }}}

# {{{ imports
import curses
import collections
import itertools
import os
import re
import subprocess
import sys
import time
import urlparse
import urwid
import fileinput
import threading

import pygments
import pygments.formatters
from urwidpygments import UrwidFormatter
from pygments.lexers import guess_lexer
# }}}

# {{{ util
def consume(iterator, n):
  '''Advance the iterator n-steps ahead. If n is none, consume entirely.'''
  collections.deque(itertools.islice(iterator, n), maxlen=0)


digit_color_re = re.compile('\033\[\d*;?\d*m')
escape_code_re = re.compile('\033\[\d*[ABCDEFGHIJK]')
backspace_re = re.compile('.\x08')

def clear_escape_codes(line):
  # clear color codes
  line = backspace_re.sub('', line)
  if line.find('\033') == -1:
    return line

  newline = digit_color_re.sub('', line)
  # jank escape code clearing methodology. need to update as new codes found
  newline = escape_code_re.sub('', newline)

  return newline

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


PROFILE=False
DEBUG=False
if DEBUG:
  debugfile = open(__name__ + ".debug", "w")
  debugfile.close()

def debug(*args):
  if DEBUG:
    debugfile = open(__name__ + ".debug", "a")
    print >> debugfile, " ".join([str(i) for i in args])
    debugfile.close()

# }}}

# {{{ input
def tokenize(lines, start_index=0):
  # http://redd.it (example URL)
  all_tokens = []
  for index, line in enumerate(lines):
    tokens = line.split()
    for token in tokens:
      all_tokens.append({
        "text" : token,
        "line" : start_index + index
      })

  return all_tokens

"http://google.com/the/first/one"

"http://yahoo.com/?asecond=eht"

# }}}

# {{{ external editor
# http://stackoverflow.com/questions/2576956/getting-data-from-external-program
def get_content_from_editor(initial=""):
    from subprocess import call
    from tempfile import NamedTemporaryFile

    editor = os.environ.get('EDITOR', 'vim')
    tfName = None

    initial = clear_escape_codes(initial)
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

# {{{ DiffLine

class DiffLine(urwid.Text):
  def __init__(self, tokens):
    try:
      if len(tokens) > 0:
        token = tokens[0]
        list_like = False
        if type(token) is list:
          list_like = True
        elif type(token) is tuple:
          list_like = True

        if list_like:
          if tokens[0] and tokens[0][1] == '-':
            tokens[0] = ('diff_del', ' ')
          if tokens[0] and tokens[0][1] == '+':
            tokens[0] = ('diff_add', ' ')


        elif type(token) is str:
          if token == '-':
            tokens[0] = ('diff_del', ' ')
          if token == '+':
            tokens[0] = ('diff_add', ' ')


    except Exception, e:
      debug("DIFF LINE EXC: ", e)


    return super(DiffLine, self).__init__(tokens)

# }}}

# {{{ TextBox widget
class TextBox(urwid.ListBox):
  def __init__(self, *args, **kwargs):
    self.last_focused_lines = []
    return super(TextBox, self).__init__(*args, **kwargs)

  def render(self, size, focus=False):
    self.highlight_middle(size, focus)
    return super(TextBox, self).render(size, focus)

  def get_middle_index(self):
    return self.middle_position

  def get_bottom_index(self):
    return self.bottom_position

  def get_top_index(self):
    return self.top_position

  def highlight_middle(self, size, focus):
    vis = self.calculate_visible(size, focus)

    top_trimmed_rows = vis[1][1]
    bot_trimmed_rows = vis[2][1]


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

    end_index = end_index or size[1]
    self.top_position = start_index
    self.bottom_position = end_index

    middle = abs(end_index - start_index) / 2 + start_index

    self.middle_position = middle
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
      self.widget = widget
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

class MenuOverlay(object):
  def __init__(self, *args, **kwargs):
    self.build_menu(*args, **kwargs)

  def build_button(self, text, value):
    def button_pressed(but):
      self.cb(text)

    button = urwid.Button(text[:40], on_press=button_pressed)
    button.button_text = value

    return button

  def build_menu(self, widget=None, title="", items=[], focused=None, cb=None, modal_keys=None):

    self.cb = cb
    walker = urwid.SimpleListWalker([self.button(token, token) for token in items])
    self.listbox = urwid.ListBox(walker)
    self.linebox = urwid.LineBox(self.listbox)

    focused_index = 0
    for index, token in enumerate(walker):
      if token.button_text == focused:
        # Need to account for the insertion of the title at the start (below), so
        # we add 1

        focused_index = index + 1

    walker.insert(0, urwid.Text(title))

    try:
      self.listbox.set_focus(focused_index)
    except:
      pass

    widget.open_overlay(self.linebox, modal_keys=modal_keys)

  def add_entry(self, entry):
    button = self.build_button(entry, entry)
    index = len(self.listbox.body)
    self.listbox.body.append(button)
    return index

  def focus(self, index):
    self.listbox.set_focus(index)
    self.listbox.set_focus_valign('middle')



def do_syntax_coloring(kv, ret, widget):
  kv.toggle_syntax_coloring()

def iterate_and_match_tokens_worker(kv, tokens, focused_line_no, func, overlay, cur_closest_distance=10000000000, closest_token=None, focused_once=False):
  debug("ITERATE AND MATCH TOKENS")
  visited = {}

  for index, token in enumerate(tokens):
    text = token['text']
    if not text in visited:
      visited[text] = True

      ret = func(text, visited)
      if ret:
        closeness = abs(focused_line_no - token['line'])
        token_index = overlay.add_entry(ret)
        if closeness < cur_closest_distance:
          cur_closest_distance = closeness
          closest_token = token_index
          debug("SETTING CLOSEST TOKEN", closeness, closest_token)

        elif closeness > cur_closest_distance and closest_token and not focused_once:
          # TIME TO FOCUS.
          debug("FOCUSING CLOSEST TOKEN", closest_token)
          overlay.focus(closest_token)
          focused_once = True



        def future_call(tokens):
          iterate_and_match_tokens_worker(kv,
            tokens,
            focused_line_no,
            func,
            overlay,
            cur_closest_distance=cur_closest_distance,
            closest_token=closest_token,
            focused_once=focused_once)

        next_tokens = tokens[index+1:]
        thread=threading.Thread(target=future_call, args=[next_tokens])
        time.sleep(0.01)
        kv.redraw_parent()
        if not kv.quit:
          thread.start()
        return


def iterate_and_match_tokens(tokens, focused_line_no, func):
  files = []
  visited = {}
  cur_closest_distance = 10000000000000
  closest_token = None

  for token in tokens:
    text = token['text']
    if not text in visited:
      visited[text] = True

      ret = func(text, visited)
      if ret:
        closeness = abs(focused_line_no - token['line'])
        if closeness < cur_closest_distance:
          cur_closest_distance = closeness
          closest_token = ret
          debug("SETTING CLOSEST TOKEN", closeness, closest_token)
        files.append(ret)

  return (files, closest_token)

CHECKED_GIT = {}
def is_git_like(obj):
  obj = obj.replace('\.', '')
  if obj in CHECKED_GIT:
    return CHECKED_GIT[obj]

  with open(os.devnull, "w") as fnull:
    args = ['git', 'show', "-s", "--pretty=oneline", obj]
    ret = subprocess.call(args, stdout=fnull, stderr=fnull)

    CHECKED_GIT[obj] = ret == 0

  return CHECKED_GIT[obj]

def do_get_git_objects(kv, ret, widget):
  def git_matcher(filename, visited):
    now = time.time()
    match = re.search('[0-9a-f]{5,40}', filename)
    if match:
      debug(filename, "IS GIT LIKE")
      if is_git_like(filename):
        return filename[:10]

  focused_line = kv.window.original_widget.get_middle_index()

  def func(response):
    contents = subprocess.check_output(['git', 'show', response])
    lines = [contents]
    widget.close_overlay()
    kv.read_and_display(lines)

  overlay = MenuOverlay(widget=widget, title="Choose a git object to open", cb=func)
  iterate_and_match_tokens_worker(kv, ret['tokens'], focused_line, git_matcher, overlay)



CHECKED_FILES = {}
def do_get_files(kv, ret, widget):

  def check_file(filename, line_no):
    numberedname = filename + ":" + str(line_no)

    if not numberedname in CHECKED_FILES:
      CHECKED_FILES[numberedname] = os.path.isfile(filename)

    if CHECKED_FILES[numberedname]:
      return numberedname
    else:
      return

  def file_matcher(text, visited):
    dir_text = text
    colon_text = text
    line_no = 0

    while dir_text:
      if not dir_text in visited:
        visited[dir_text] = True
        filename = check_file(dir_text, line_no)
        if filename:
          return filename

      text_dirs = dir_text.split('/')
      text_dirs.pop(0)
      dir_text = '/'.join(text_dirs)

    while colon_text:
      if not colon_text + ":" + str(line_no) in visited:
        visited[colon_text + str(line_no)] = True
        if check_file(colon_text, line_no):
          return colon_text + ":" + str(line_no)

      text_dirs = colon_text.split(':')
      line_no = text_dirs.pop()
      try:
        line_no = int(line_no)
      except:
        line_no = 0

      colon_text = ':'.join(text_dirs)

  focused_line = kv.window.original_widget.get_middle_index()
  def func(response):
    split_resp = response.split(':')
    line_no = 0
    if len(split_resp) == 2:
      response, line_no = split_resp
    try:
      with open(response, "r") as f:
        contents = list(f.readlines())
        widget.close_overlay()
        kv.read_and_display(contents)
    except Exception, e:
      debug("EXCEPTION", e)

    kv.window.original_widget.set_focus(int(line_no))

  def open_in_editor(kv, ret, widget):
    box = kv.window.widget.original_widget
    button, index = box.get_focus()

    # assuming first line is not a file
    if not index:
      return

    filename = button.button_text
    split_resp = filename.split(':')
    line_no = 0
    if len(split_resp) == 2:
      filename, line_no = split_resp
    subprocess.call([os.environ['EDITOR'], filename])

    widget.close_overlay()

  modal_keys = {
    "e" : {
      "fn" : open_in_editor,
      "help" : "",
    }
  }
  overlay = MenuOverlay(widget, title="Choose a file to open. ('e' to open in editor)",
    cb=func, modal_keys=modal_keys)
  iterate_and_match_tokens_worker(kv, ret['tokens'], focused_line, file_matcher, overlay)


def do_get_urls(kv, ret, widget=None):
  tokens = ret['tokens']

  def url_matcher(text, visited):
    match = re.search("^\W*(https?://[\w\./]*|www.[\w\./\?&\.]*)", text)
    if match:
      return match.group(1)

  focused_line = kv.window.original_widget.get_middle_index()
  def func(response):
    if not response.startswith('http'):
      response = "http://%s" % response
    subprocess.Popen(["/usr/bin/xdg-open", response])
    widget.close_overlay()

  overlay = MenuOverlay(widget, title="Choose a URL to open", cb=func)
  iterate_and_match_tokens_worker(kv, ret['tokens'], focused_line, url_matcher, overlay)

def do_exit():
  raise urwid.ExitMainLoop()


def do_print(kv, ret, scr):
  def func():
    print ret['joined']

  kv.after_urwid.append(func)
  do_exit()

def do_back_or_quit(kv, ret, widget):
  if widget.overlay_opened:
    widget.close_overlay()
  elif kv.stack:
    kv.restore_last_display()
  else:
    raise urwid.ExitMainLoop()

def do_close_overlay_or_quit(kv, ret, widget):
  if  widget.overlay_opened:
    widget.close_overlay()
  else:
    raise urwid.ExitMainLoop()

def do_quit(kv, ret, scr):
  raise urwid.ExitMainLoop()

def do_pop_stack(kv, ret, scr):
  kv.restore_last_display()

def do_edit_text(kv, ret, widget):
  lines = get_content_from_editor(ret["joined"])
  kv.read_and_display(lines)

def do_diff_xsel(kv, ret, widget):
  import difflib
  lines = [clear_escape_codes(line) for line in kv.ret['lines']]
  args = [ 'xsel' ]
  compare = None

  try:
    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    compare = p.communicate()[0].strip()
  except:
    kv.display_status_msg(('diff_del', "xsel is required for diffing buffers"))


  if compare:
    compare_lines = [line + "\n" for line in compare.split("\n")]
    comparison = difflib.unified_diff(
      compare_lines, lines,
      fromfile="clipboard", tofile="buffer")

    compared = list(comparison)
    if not len(compared):
      compared = ["no difference between clipboard and buffer!"]
    kv.read_and_display(compared)

    kv.display_status_msg("displaying diff of the xsel buffer (before) and current buffer (after)")
  else:
    kv.display_status_msg("no diff, to speak of")


def do_yank_text(kv, ret, widget):
  lines = [clear_escape_codes(line) for line in kv.ret['lines']]

  debug("YANKING", len(lines), "LINES")

  args = [ 'xsel', '-pi' ]

  try:
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write("".join(lines))

    p.communicate()
    kv.display_status_msg("saved buffer to clipboard")
  except:
    kv.display_status_msg(('diff_del', "xsel is required to save the buffer to a clipboard"))


def do_next_search(kv, ret, widget):
  kv.find_and_focus()

def do_prev_search(kv, ret, widget):
  kv.find_and_focus(reverse=True)

def do_scroll_top(kv, ret, widget):
  widget.original_widget.set_focus_valign('top')
  widget.original_widget.set_focus(0)

def do_scroll_bottom(kv, ret, widget):
  widget.original_widget.set_focus_valign("bottom")
  kv.readjust_display(widget.original_widget, len(widget.original_widget.body))

def do_general(kv, ret, widget):
  debug("Entering general mode")
  setup_general_hooks()

def do_pipe_prompt(kv, ret, widget):
  debug("Entering pipe mode")
  kv.open_command_line('!')

def do_search_prompt(kv, ret, widget):
  debug("Entering search mode")
  kv.open_command_line('/')

def do_command_prompt(kv, ret, widget):
  debug("Entering command mode")
  kv.open_command_line(':')

def handle_command(kv, prompt, command):
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
    handle_command(kv, kv.prompt_mode, cmd)

  kv.close_command_line()
# }}}

# {{{ help
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
    "help" : "enter command mode",
  },
  "/" : {
    "fn" : do_search_prompt,
    "help" : "enter interactive search"
  },
  "!" : {
    "fn" : do_pipe_prompt,
    "help" : "pipe current buffer through an external command"
  },
  "Q" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "quit kit / close current overlay"
  },
  "q" : {
    "fn" : do_back_or_quit,
    "help" : "close current buffer. if there are no buffers left, quit"
  },
  "p" : {
    "fn" : do_print,
    "help" : "print buffer to stdout and quit"
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
  "d" : {
    "fn" : do_diff_xsel,
    "help" : "diff the current buffer with the X clipboard"
  },
  "y" : {
    "fn" : do_yank_text,
    "help" : "save the current buffer to the X clipboard with xsel"
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
    "help" : "visit previously opened buffer"
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
      obj['oldfn'](*args, **kwargs)
      _key_hooks = CURSES_HOOKS

    obj['oldfn'] = obj['fn']
    obj['fn'] = replacement

  build_replacement()


def setup_general_hooks():
  global _key_hooks
  _key_hooks = GENERAL_HOOKS

# }}}

# {{{ color setup
palette = [
  ('highlight', 'white', 'dark gray'),
  ('banner', 'black', 'white'),
  ('default', 'black', 'white'),
  ('diff_add', 'white', 'light green'),
  ('diff_del', 'white', 'light red'),
  ('streak', 'black', 'dark red'),
  ('bg', 'black', 'dark blue'),
]
COLORS = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
COLOR_NAMES = {
   "black": "black",
   "red": "dark red",
   "green": "dark green",
   "yellow": "brown",
   "blue": "dark blue",
   "magenta": "dark magenta",
   "cyan": "dark cyan",
   "white" : "white"

}
for color in COLORS:
  palette.append(('%s_bg' % (color), 'black', COLOR_NAMES[color]))
  palette.append(('%s_fg' % (color), COLOR_NAMES[color], 'black'))

  for jcolor in COLORS:
    palette.append(('%s_%s' % (color, jcolor), COLOR_NAMES[color], COLOR_NAMES[jcolor]))


# }}}

# {{{ main viewer class


_lexer_fname_cache = {}
ESCAPE_CODE = re.compile("[KABCDEF]")
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
    self.syntax_colored = False
    self.fname = None
    self.last_repaint = time.time()
    self.ret = None
    self.quit = False
    self.color_table = None
    self.screen_lock = threading.Lock()
    self.last_redraw = time.time()

    self.build_color_table()


  def reset_line_stats(self):
    self.ret = {}
    self.ret['maxx'] = 0
    self.ret['syntax_lines'] = 0
    self.ret['maxy'] = 0
    self.ret['numlines'] = 0
    self.ret['has_content'] = False
    self.ret['joined'] = ""
    self.ret['lines'] = []
    self.ret['tokens'] = []

  def update_pager(self, line_count=None):
    try:
      # This can throw if we aren't in text editing mode
      middle_line = self.window.original_widget.get_middle_index()
      start_line = self.window.original_widget.get_top_index()
      end_line = self.window.original_widget.get_bottom_index() + 1
    except Exception, e:
      return

    if not line_count:
      if self.syntax_colored:
        line_count = self.ret['syntax_lines']
      if not self.syntax_colored:
        line_count = self.ret['maxy']

    if not line_count:
      fraction = 0
      return

    fraction = min(float(middle_line) / float(line_count) * 100, 100)

    line_no = middle_line
    if fraction < 20:
      fraction = max(float(start_line) / float(line_count) * 100, 0)
      line_no = start_line

    if fraction > 20:
      fraction = min(float(end_line) / float(line_count) * 100, 100)
      line_no = end_line
    fraction = int(fraction)

    line_no = min(end_line, line_count)

    pager_msg = "%s/%s (%s%%)" % (line_no, line_count, fraction)

    if len(self.stack):
      pager_msg = "%s %s" % (pager_msg, len(self.stack) * '=')

    self.display_pager_msg(pager_msg)

    self.redraw_parent()

  def run(self, stdscr):
    # We're done with stdin,
    # now we want to read input from current terminal
    def handle_input(keys, raw):
      global _key_hooks
      unhandled = []
      debug("HANDLING INPUT", repr(keys))

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

      self.loop.event_loop.alarm(0.05, self.update_pager)
      if was_general:
        _key_hooks = CURSES_HOOKS
        return []

      return unhandled

    def unhandle_input(key):
      self.last_repaint = time.time()
      if self.in_command_prompt:
        if key == 'enter':
          do_command_entered(self, self.ret, widget)
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

    self.command_line = urwid.WidgetPlaceholder(urwid.Text(""))
    self.window = widget

    self.panes = urwid.Frame(widget, footer=self.command_line)

    self.pager = urwid.Text("")
    self.prompt = urwid.Edit()

    self.open_command_line()
    self.close_command_line()
    self.loop = urwid.MainLoop(self.panes, palette, unhandled_input=unhandle_input, input_filter=handle_input)

    def pipe_cb(data):
      return True

    self.redraw_pipe = self.loop.watch_pipe(pipe_cb)

    self.display_status_msg(('banner', "Welcome to the kitchen sink pager. Press '?' for shortcuts"))

    self.display_lines([])
    self.read_and_display()
    # Don't re-open the TTY until after reading stdin
    with open("/dev/tty") as f:
      os.dup2(f.fileno(), 0)

    if self.ret['has_content']:
      try:
        self.loop.run()
      except Exception, e:
        debug("EXCEPTION (QUITTING)", e)
        self.quit = True
      finally:
        self.quit = True

  def redraw_parent(self, force=False):
    now = time.time()
    if now - self.last_redraw > 0.2:
      os.write(self.redraw_pipe, "REDRAW THYSELF\n")
      self.last_redraw = now

  # for reals. this is a stub, but used to get an entry point back into the
  # main loop and redraw the screen
  def repaint_screen(self, force=False):
    pass


  def open_command_line(self, mode=':'):
    self.prompt_mode = mode
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(self.prompt_mode)), ("weight", 1, self.prompt)])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = True
    self.panes.set_focus('footer')
    self.prompt.set_edit_text("")

  def close_command_line(self, mode=':'):
    self.prompt.set_edit_text("")
    prompt_cols = urwid.Columns([
      ("fixed", 1, urwid.Text(self.prompt_mode)),
      ("weight", 1, self.prompt),
      ("fixed", 25, urwid.Padding(self.pager, align='right', min_width=10)),
    ])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = False
    self.panes.set_focus('body')

  def build_color_table(self):

    if not self.color_table:
      table = {"[0":'default'}

      for index, color in enumerate(COLORS):
        table["[%s" % (30 + index)] = "%s_fg" % color
        table["[1;%s" % (30 + index)] = "%s_fg" % color
      for index, color in enumerate(COLORS):
        table["[%s" % (40 + index)] = "%s_bg" % color
        table["[%s" % (40 + index)] = "%s_bg" % color
      for index, color in enumerate(COLORS):
        for jindex, jcolor in enumerate(COLORS):
          table["[%s;%s" % (30+index, 40 + jindex)] = "%s_%s" % (color, jcolor)

      self.color_table = table

    return self.color_table

  def escape_ansi_colors(self, lines, syntax_colored=False):
    wlist = []

    table = self.color_table
    for line in lines:
      col = 0
      stripped = line.lstrip()
      col = len(line) - len(stripped)
      markup = []
      stripped = backspace_re.sub('', line.rstrip())
      newline = False
      if not syntax_colored:
        if stripped.find("\033") >= 0:
          split_strip = stripped.split("\033")
          markup.append(split_strip[0])
          for at in split_strip[1:]:

            # Try colors
            split_at = at.split("m",1)

            if len(split_at) > 1:
              attr, text = split_at
            else:
              # If not a color but an escape code, just swallow it
              text = at
              split_index = ESCAPE_CODE.search(text).start()
              if split_index >= 0:
                split_at = [at[:split_index+1], at[split_index+1:]]
                text = split_at.pop()

              attr = None

            if text:
              if attr in table:
                markup.append((table[attr], text))
              else:
                markup.append((None, text))
        else:
          markup = stripped

        line = markup
        if not line:
          newline = True

      else:
        line = (None, line)

      if line:
        wlist.append(line)
      if newline:
        wlist.append('')

    return [ urwid.Text(line) for line in wlist ]

  def new_display(self):
    self.syntax_colored = False
    self.previous_widget = None
    widget = self.window
    self.walker = urwid.SimpleListWalker([])
    text = TextBox(self.walker)
    widget.original_widget = text

  def display_lines(self, lines=[]):
    self.new_display()
    lines = "".join(lines).split("\n")
    wlist = self.escape_ansi_colors(lines)
    self.walker.extend(wlist)

  def get_focus_index(self, widget):
    try:
      return widget.get_middle_index()
    except:
      return 0

  def readjust_display(self, listbox, index):
    if self.last_search_token:
      text, attr = self.last_search_token.get_text()
      self.last_search_token.set_text((None, text))


      self.last_search_token = listbox.body[min(self.last_search_index, len(listbox.body))]
      new_text, attr = self.last_search_token.get_text()
      self.last_search_token.set_text(('highlight', new_text))

    max_cols = min(len(listbox.body), self.ret['maxy']) - 1
    new_index = max(min(max_cols, index), 0)
    debug("ADJUSTING DISPLAY", listbox, len(listbox.body), index, new_index, self.syntax_colored)
    listbox.set_focus(new_index)
    listbox.set_focus_valign('middle')
    self.update_pager()

  def read_line(self, line, ret=None):
    if not ret:
      ret = self.ret

    eline = clear_escape_codes(line)

    if not 'is_diff' in ret:
      if line.find('diff --git') >= 0:
        ret['is_diff'] = True

    tokens = ret['tokens']
    for index, token in enumerate(eline.split()):
      tokens.append({
        "line": ret['maxy'] + index,
        "text" : token })

    ret['maxx'] = max(ret['maxx'], len(eline))
    ret['maxy'] += 1
    ret['numlines'] += line.count("\n")
    ret['has_content'] = True
    ret['lines'].append(line)

  def read_while_displaying_lines(self, lines=None, walker=None, ret=None, syntax_colored=None):
    if not walker:
      walker = self.walker

    if not ret:
      ret = self.ret

    if not lines:
      gen = fileinput.input()
    else:
      gen = iter(lines)

    if syntax_colored is None:
      syntax_colored = self.syntax_colored

    index = 0
    scheduled_work = False
    append_lines = []
    for line in gen:
      index += 1
      self.read_line(line, ret)
      append_lines.append(line)

      if self.quit:
        sys.exit(0)

      if not index % 100:
        wlines = self.escape_ansi_colors(append_lines, syntax_colored)
        for wline in wlines:
          if self.quit:
            sys.exit(0)
          walker.append(wline)

        def future_call(lines):
          self.read_while_displaying_lines(lines, walker, ret, syntax_colored)
          self.update_pager()

        next_lines = list(gen)
        if len(next_lines):
          thread = threading.Thread(target=future_call, args=[next_lines])
          time.sleep(0.01)
          if not self.quit:
            thread.start()
          scheduled_work = True
        break

    if not scheduled_work:
      wlines = self.escape_ansi_colors(append_lines, syntax_colored)
      self.ret['syntax_lines'] += len(wlines)
      for wline in wlines:
        walker.append(wline)

      ret['joined'] = "".join(ret['lines'])
      self.update_pager()


  def read_and_display(self, lines=None):
    del self.walker[:]

    if self.ret:
      self.stack.append(self.ret)

    self.reset_line_stats()
    self.new_display()

    self.ret['focused_index'] = self.get_focus_index(self.window.original_widget)

    if lines:
      resplit_lines = ["%s\n" % line for line in "".join(lines).split("\n")]
      resplit_lines[-1] = resplit_lines[-1].rstrip()
      lines = resplit_lines
    self.read_while_displaying_lines(lines)

  def restore_last_display(self):
    if self.stack:
      self.ret = self.stack.pop()

      self.display_lines(self.ret['lines'])
      if 'focused_index' in self.ret:
        self.readjust_display(self.window.original_widget, self.ret['focused_index'])

  def pipe_and_display(self, command):
    import shlex
    data_in = self.ret['joined']
    args = shlex.split(command)
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write(data_in)

    stdout = p.communicate()[0]
    self.read_and_display([stdout])

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
      self.display_status_msg("Pattern not found. Wrapping")
      found = find_word(tokens, 0)

      if not found:
        self.display_status_msg("Pattern not found  (Press RETURN)")

  def syntax_msg(self):
    if self.syntax_colored:
      self.display_status_msg("Setting syntax to %s" % self.syntax_lang)
    else:
      self.display_status_msg("Disabling syntax coloring")

  def toggle_syntax_coloring(self):
    # a shortcut
    if self.previous_widget:
      original_text = self.window.original_widget
      focused_index = self.get_focus_index(original_text)
      self.window.original_widget = self.previous_widget
      self.previous_widget = original_text

      debug("SYNTAX COLORING PREV WIDGET")

      self.syntax_colored = not self.syntax_colored
      debug("FOCUSED INDEX", focused_index)
      self.readjust_display(self.window.original_widget, focused_index)
      self.syntax_msg()

      return

    self.enable_syntax_coloring()


  # one time setup for syntax coloring
  def enable_syntax_coloring(self):
    debug("INITIALIZING SYNTAX COLORED WIDGET")
    walker = urwid.SimpleListWalker([])

    self.previous_widget = self.window.original_widget
    listbox = TextBox(walker)
    self.window.original_widget = listbox
    self.syntax_colored = True
    focused_index = self.get_focus_index(self.previous_widget)

    formatter = UrwidFormatter()
    def handle_token(token, formatted_line, diff=False):
      text = token[1]
      if not text:
        return

      if text.find('\n') >= 0:
        split_line = clear_escape_codes(text)
        while split_line:
          n = split_line.find('\n')
          if n >= 0:
            last_word = split_line[:n]
            split_line = split_line[n+1:]
            formatted_line.append(last_word)
            if diff:
              walker.append(DiffLine(list(formatted_line)))
            else:
              walker.append(urwid.Text(list(formatted_line)))

            del formatted_line[:]
          else:
            formatted_line.append((token[0], split_line))
            break
      else:
        token = (token[0], clear_escape_codes(token[1]))
        formatted_line.append(token)

      # end of handle_token function

    def add_diff_lines_to_walker(ret, index, walker, clear_walker=True, cb=None, fname=None):

      if clear_walker:
        walker[:] = [ ]

      wlines = []
      # stupid \n ending required...
      iterator = itertools.count(index)
      for index in iterator:

        if index >= len(ret['lines']) or self.quit:
          break

        line = clear_escape_codes(ret['lines'][index])

        if line.startswith("diff --git"):
          diff_index = index

          commit_lines = [ line ]
          def add_line():
            commit_lines.append(clear_escape_codes(ret['lines'][iterator.next()]))
            return 1
            # doh. even though iterator is consuming it, we need this for later

          index += add_line() # Author
          index += add_line() # Date
          index += add_line() # Blah

          index += 1


          # Look upwards for the commit line (find the first line that starts with Author and Date)
          # and put them in commit_lines

          author_index = None

          for windex, wline in enumerate(wlines):
            if wline.startswith("Author:"):
              author_index = windex

          if author_index:
            commit_lines = wlines[author_index-1:] + commit_lines
            wlines = wlines[:author_index-1]

          if wlines:
            debug("ADDING SYNTAX LINES", wlines, self.fname)
            add_lines_to_walker(wlines, walker, self.fname, diff=True)

          if commit_lines:
            debug("ADDING COMMIT LINES", commit_lines, self.fname)

            if not clear_walker and author_index:
              walker.append(urwid.Text(""))
            add_lines_to_walker(commit_lines, walker, None, skip_colors=True, diff=True)

          # next fname output
          self.fname = line.split().pop()
          debug("SETTING FNAME TO", self.fname)

          def future_call(index, walker):
            self.update_pager()
            self.ret['syntax_lines'] = index
            add_diff_lines_to_walker(ret, index, walker, clear_walker=False, cb=cb)

          thread = threading.Thread(target=future_call, args=(index, walker))
          time.sleep(0.001)
          if not self.quit:
            thread.start()
          return
        else:
          wlines.append(line)

      # When we make it to the way end, put the last file contents in
      add_lines_to_walker(wlines, walker, self.fname, diff=True)

      if cb:
        cb()

      self.ret['syntax_lines'] = index
      # This is when we are finally done. (For reals)
      self.update_pager()

    def add_lines_to_walker(lines, walker, fname=None, diff=False, skip_colors=False):
      if len(lines):
        lexer = None
        forced = False

        if not fname and skip_colors:
          debug("LINES BEFORE LEXER", lines)
          debug("SKIPPING COLORING", fname, diff)
          lines = self.escape_ansi_colors([line.rstrip() for line in lines])
          self.syntax_lang = "None"
          walker.extend(lines)
          return

        output = "".join(lines)
        try:
          forced = True
          if not fname in _lexer_fname_cache:
            _lexer_fname_cache[fname] = pygments.lexers.get_lexer_for_filename(fname)

          lexer = _lexer_fname_cache[fname]
        except:
          pass

        if not lexer:
          lexer = guess_lexer(output)

        if diff and forced:
          self.syntax_lang = "git diff"
          debug("LEXER (FORCED) ", lexer)
        else:
          score = lexer.__class__.analyse_text(output)
          self.syntax_lang = lexer.name
          debug("LEXER (TRIED: %s) and (GUESSED) SCORE" % (fname), lexer, score)
          if score < 0.3:
            # COULDNT FIGURE OUT A GOOD SYNTAX HIGHLIGHTER
            # DISABLE IT
            lexer = pygments.lexers.get_lexer_by_name('text')
            self.syntax_lang = "none. (Couldn't auto-detect a syntax)"

            lines = self.escape_ansi_colors([line.rstrip() for line in lines], self.syntax_colored)
            walker.extend(lines)
            return

        if lexer.__class__ is pygments.lexers.TextLexer:
          debug("TEXT LEXER! DISABLING")
          lines = self.escape_ansi_colors(["%s" % line.rstrip() for line in lines], self.syntax_colored)
          walker.extend(lines)
          return

        tokens = lexer.get_tokens(output)

        # Build the syntax output up line by line, so that it can be highlighted
        # one line at a time
        formatted_tokens = list(formatter.formatgenerator(tokens))
        formatted_line = []

        for token in formatted_tokens:
          handle_token(token, formatted_line, diff)

        if formatted_line:
          walker.append(urwid.Text(list(formatted_line)))


    lines = self.ret['lines']
    if 'is_diff' in self.ret:
      debug("ADDING DIFF LINES TO WALKER")
      def make_cb():
        original_widget = self.window.original_widget
        started = time.time()
        def func():
          ended = time.time()
          debug("TIME TOOK", ended - started)
          if ended - started < 1:
            self.readjust_display(original_widget, focused_index)

          if not self.syntax_colored:
            self.update_pager()

        return func
      add_diff_lines_to_walker(self.ret, 0, walker, cb=make_cb())
    else:
      wlines = [clear_escape_codes(line) for line in lines]
      add_lines_to_walker(wlines, walker, None)
      self.readjust_display(self.window.original_widget, focused_index)

    self.syntax_msg()


  def display_status_msg(self, msg):
    if type(msg) is str:
      msg = ('highlight', msg)
    self.prompt.set_caption(msg)
    self.prompt.set_edit_text("")
    self.clear_edit_text = True

  def display_pager_msg(self, msg):
    if type(msg) is str:
      msg = ('highlight', msg)
    self.pager.set_text(msg)

def _run():
  kv = Viewer()
  curses.wrapper(kv.run)
  for after in kv.after_urwid:
    if hasattr(after, '__call__'):
      try:
        after()
      except Exception, e:
        raise e

def run():
  if PROFILE:
    import cProfile
    cProfile.run("_run()", "restats")
  else:
    _run()

if __name__ == "__main__":
  run()
# }}}

# vim: set foldmethod=marker
