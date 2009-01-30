#!/usr/bin/env python
"""
Parses irc logs to gather urls,
checks urls against craplist,
identifies poster and tags,
if possible, posts to delicious.
"""

__version__ = "0.02"
__copyright__ = "Copyright (c) 2007-2009 GCU"
__license__ = "BSD"

import sys
import re
import os
import optparse
import yaml
import webbrowser
from urlparse import urlparse
import pprint

import urwid
import urwid.curses_display
#kinda gruika

#import deliciousapi as deliciousmodule
import deliciousapi

from deliciousapi import DeliciousAPI

def getpagetitle(url):
    import urllib2
    try:
        furl = urllib2.urlopen(url)
        contenu = furl.read()
        letitre = titre.findall(contenu)
        if letitre:
            return letitre[0]
        else:
            return None
    except:
        return None


class PatternList(object):
    """
    A Patternlist is a list of regular expressions. the 'in' operator
    allows a string to be compared against each expression (using search
    NOT match)
    """
    # source :  python cookbook

    def __init__(self, patterns = []):
        self.patterns = []
        for p in patterns:
            self.add(p)

    def add(self, pattern):
        pat = re.compile(pattern)
        self.patterns.append(pat)

    def __contains__(self, item):
        ret = False
        for p in self.patterns:
            if p.search(item):
                ret= True
                break
        return ret



def filterurl(line):
    """Return True if url in line, False otherwise"""
    url = (r'https?://','www\.')
    urlpattern = PatternList(url)
    return (line in urlpattern)

def filtercrap(line):
    """Return True if line not in crapfile, False otherwise"""
    crap = [url.rstrip() for url in open('crap.txt').readlines() if url[0] !='#']
    crappattern = PatternList(crap)
    return (line not in crappattern)

def getfile(infile=None):
    """Return a read-opened file handler, sys.stdin if arg is None"""
    if not infile:
        fin = sys.stdin
    elif isinstance(infile, str):
        fin = open(infile, 'r')
    else:
        fin = infile
    res = fin

    return res

def buildlistfromfile(infile, verbose=True, conf={}):
    """Return a list of lines containing URLs in infile"""
    res = infile
    for func in (filterurl,filtercrap):
        res = filter(func, res)
    infile.close()

    lutin = re.compile(r'\d{2}:\d{2} <?[ \+@]?(.*?)>? ')
    url = re.compile(r'(https?://.*?|www\..*?)[ ,)\n]')
    tags = re.compile(r' #(.*?)#[ ,\n]')

    liste = []
    for line in res:
        if verbose:
            print >> sys.stderr, line,
        for i in url.findall(line):
            if i.startswith('www'):
                i = 'http://%s' % i
            if i in [u['url'] for u in liste]:
                continue
            d = {}
            d['url'] = i
            taglist = []
            _lut = lutin.findall(line)
            if (len(_lut)):
                taglist.append(lutin.findall(line)[0])
                if tags.findall(line):
                    taglist.extend(tags.findall(line)[0].split(','))
                d['tags'] = taglist
                liste.append(d)

    return liste

class UrlWidget(urwid.WidgetWrap):
    """URL Widget for urwid"""
    def __init__(self, item, size, unfocused, focused=None):
        self.url = item['url']
        self.title = None
        self.tags = item['tags']
        self.lutin = self.tags[0]
        self.scrapped = False
        self.posted = False
        w = urwid.Text('%1s%1s %s' % ('s'*self.scrapped,
                                    'p'*self.posted,
                                    self.url[:size[0]-3]))
        self.widget = w
        w = urwid.AttrWrap(w, unfocused, focused)
        urwid.WidgetWrap.__init__(self, w)
        self.size = size

    def keypress(self, pos, key):
        return key

    def selectable(self):
        return True

    def post(self):
        """sets tposted"""
        self.posted = not self.posted
        self.widget.set_text('%1s%1s %s' % (\
                'p'*self.scrapped,
                'p'*self.posted,
                 self.url[:self.size[0]-3])
        )

    def retag(self):
        """sets taggued"""
        self.scrapped = not self.scrapped
        self.widget.set_text('%1s%1s %s' % (\
                's'*self.scrapped,
                'p'*self.posted,
                 self.url[:self.size[0]-3])
        )

    def scrap(self):
        """sets scrapped"""
        self.scrapped = not self.scrapped
        self.widget.set_text('%1s%1s %s' % (\
                's'*self.scrapped,
                'p'*self.posted,
                 self.url[:self.size[0]-3])
        )


class MainWindow(object):
    """Our main window"""

    ui = None
    def __init__(self, conf, urls):
        self.urls = urls
        self.conf = conf
        self.ui = urwid.curses_display.Screen()
        self.dh = DeliciousAPI(
                conf.get('delicious', 'login'),
                conf.get('delicious', 'pass'))

        self.scraplist = []
        self.view = None

# {{{ def: build
    def build(self):
        """build the widgetz"""
        self.ui.register_palette([
                ('body', 'black', 'light gray'),
                ('selected', 'white', 'dark blue', 'standout'),
                ('header', 'yellow', 'black', 'standout'),
        ])
        self.ui.run_wrapper(self.run)
# }}}

# {{{ def: redisplay
    def redisplay(self):
        """if the display iz br0kmut"""
        self.ui.draw_screen(self.size, self.view.render(self.size, focus=1))
# }}}

# {{{ def: run
    def run(self):
        """here we startz"""
        print "started"
        self.size = self.ui.get_cols_rows()
        itemlist = [UrlWidget(line, self.size, None,'selected') for line in urls]
        self.items = urwid.PollingListWalker(itemlist)
        self.listbox = urwid.ListBox(self.items)
        self.instruct = urwid.Text("[v]iew [r]etag [i]nfos [p]ost [s]crap [q]quit")
        self.header = urwid.AttrWrap(self.instruct, 'header')
        self.tagedit = urwid.Edit("")
        self.footer = urwid.AttrWrap(self.tagedit,'header')
        self.view = urwid.Frame(self.listbox, self.header, self.footer)

        while 1:
            self.redisplay()
            keys = None
            focus, _ign = self.listbox.body.get_focus()

            while not keys:
                keys = self.ui.get_input()
            for k in keys:
                if k in ('q','Q'):
                    # quit
                    crapfile = open(self.conf.get('scraplist', 'a+'))
                    crapfile.writelines(scraplist)
                    crapfile.close()
                    return

                if k in ('s','S'):
                    # scrap
                    self.scrap(focus, self.conf.get('scraplist'))

                if k in ('i','I'):
                    self.display_url_info(focus)

                if k in ('r','R','enter'):
                    self.retag(focus)

                if k in ('p','P'):
                    self.post(focus)

                if k in ('v','V'):
                    # view
                    webbrowser.open_new_tab(focus.url)
                    self.ui.clear()
                if "window resize" in keys:

                    self.size = self.ui.get_cols_rows()
                    self.redisplay()
                self.view.keypress(self.size, k)
# }}}

# {{{ def: scrap
    def scrap(self, item, liste):
        """adds an item to teh scapz list"""
        item.scrap()

        domain = urlparse(item.url).netloc
        domain = re.escape(domain)
        domain = '%s\n' % domain
        if item.scrapped:
            self.scraplist.append(domain)
        else:
            self.scraplist.remove(domain)
# }}}

# {{{ def: post
    def post(self, item):
        """post teh item at delicious"""
#    def posts_add(self, url, description, extended="", tags="", dt="",
#            replace="no", shared="yes", **kwds):
#        """Add a post to del.icio.us. Returns a `result` message or raises an
#        ``DeliciousError``. See ``self.request()``.
#
#        &url (required)
#            the url of the item.
#        &description (required)
#            the description of the item.
#        &extended (optional)
#            notes for the item.
#        &tags (optional)
#            tags for the item (space delimited).
#        &dt (optional)
#            datestamp of the item (format "CCYY-MM-DDThh:mm:ssZ")."""
        if not item.title:
            item.title = getpagetitle(item.url) or self.inputwidget("title:")
#        self.dh.post(item.url, title, tags = ' '.join(item.tags))
        item.post()

# }}}

# {{{ def get_url_info

    def display_url_info(self, item):
        """shows the url infos in ``statusbar''"""



    def inputwidget(self, caption):
        """returns a text entered"""
        self.view.set_focus('footer')
        self.tagedit.set_edit_pos(len(self.tagedit.edit_text))
        self.tagedit.set_text(caption)
        while True:
            keys = self.ui.get_input()
            self.redisplay()
            for k in keys:
                if k == "enter":
                    self.view.set_focus('body')
                    ret = self.tagedit.edit_text
                    self.tagedit.edit_text = ""
                    self.redisplay()
                    return ret
                self.view.keypress(self.size, k)


    def retag(self, item):
        """retags teh current url"""
        self.view.set_focus('footer')
        tag = self.inputwidget('tags:').strip()
        item.tags = [s.strip() for s in tag.split(',')]


if __name__ == "__main__":
    # get options from teh command line

    p = optparse.OptionParser(
        description='Parses irc logfile to find urls to be posted to del.icio.us',
        prog='gculicious',
        version='gculicious 0.01',
        usage='gculicious.py logfile',)
    p.add_option('-v', '--verbose', action ='store_true', help='returns original line in addition to filtered elements')
    options, arguments = p.parse_args()
    if len(arguments) > 1:
        p.print_help()
        exit


    # gets the configuration
    print "Reading config file... "
    config = yaml.load(file('./irclicious.yml'))
    pprint.pprint(config)
    if len(arguments) == 1:
        fich = getfile(arguments[0])
    else:
        fich = getfile()


    # parses the file
    print "Building url list... "
    urls = buildlistfromfile(fich, options.verbose, config)

    # launches the curswin
    mw = MainWindow(config, urls)
    mw.build()
