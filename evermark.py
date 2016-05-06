#!/usr/bin/env python
# coding: utf-8

import os
import cgi
import time
import datetime
import json
import ConfigParser
import traceback
import logging

import chardet
import markdown2
import premailer

import evernote.edam.type.ttypes as Types
import evernote.edam.notestore.NoteStore as NoteStore
import evernote.edam.userstore.constants as UserStoreConstants
from evernote.api.client import EvernoteClient

log = None
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'


def current_time():
    return datetime.datetime.now().strftime(TIME_FORMAT)


def modify_time(fpath):
    return time.strftime(TIME_FORMAT, time.localtime(os.path.getmtime(fpath)))


def compare(str_time1, str_time2):
    time1 = time.strptime(str_time1, TIME_FORMAT)
    time2 = time.strptime(str_time2, TIME_FORMAT)
    timestamp1 = time.mktime(time1)
    timestamp2 = time.mktime(time2)
    return timestamp1 - timestamp2


class EverMark(object):
    """
    Standard usage should be like:
        1. em = EverMark(conf='confi.ini')
        2. em.login()
        3. sync(rpath, sub_dir, fname)   rpath -> root sync path, sub_dir -> notebook, fname -> note
    """
    def __init__(self, conf=os.path.join(os.path.abspath(os.path.dirname(__file__)), 'conf.ini')):  # Default configure file is in the same directory of evermark.py
        try:
            log_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logs')
            if not os.path.exists(log_path):
                os.mkdir(log_path)
            log_file_path = os.path.join(log_path, 'evermark_sync.log')
            logging.basicConfig(filename=log_file_path, format='%(asctime)-15s [%(levelname)s] %(message)s')
            global log
            log = logging.getLogger('sync')
            log.setLevel(logging.INFO)

            cf = ConfigParser.SafeConfigParser({'test': 'no',  # Test locally
                                                'account_type': 'evernote',
                                                'root': os.path.abspath(os.path.dirname(__file__)),  # The directory that EverMark is installed to .
                                                'auth_token': '',
                                                'ignore_dirs': '',
                                                'input_encoding': '',
                                                'style': 'github',
                                                'log_level': 'info'})
            cf.read(conf)

            opt = cf.get('main', 'log_level')
            if opt == 'debug':
                log.setLevel(logging.DEBUG)

            log.info('=' * 10 + 'EverMark Sync Start' + '='*10)

            opt = cf.get('main', 'test')
            self._test = True if (opt == 'yes') else False

            self.account_type = cf.get('main', 'account_type')
            self.root_path = cf.get('main', 'root')
            self.auth_token = cf.get('main', 'auth_token')
            self.input_encoding = cf.get('main', 'input_encoding')
            self.style = cf.get('main', 'style')

            opt = cf.get('main', 'ignore_dirs')
            if opt:
                self.ignore_sub_dirs = opt.strip().split(',')
            else:
                self.ignore_sub_dirs = []

            log.debug('account_type:' + self.account_type)
            log.debug('root_path:' + self.root_path)
            log.debug('auth_token:' + self.auth_token)
            log.debug('ignore_dirs:' + str(self.ignore_sub_dirs))
            log.debug('style:' + self.style)

        except:
            log.critical(traceback.format_exc())
            exit(0)

        self.css_str = ''
        css_file_path = os.path.join(self.root_path, 'css/' + self.style + '.css')
        log.debug('Load CSS from file: ' + css_file_path)
        with open(css_file_path) as f:
            self.css_str = f.read().decode('utf-8')

        # Create directory for html logs
        self.html_log_path = os.path.join(self.root_path, 'logs/html')
        if not os.path.exists(self.html_log_path):
            os.mkdir(self.html_log_path)

        self.note_sync_status_file_path = os.path.join(self.root_path, 'status.json')
        self.note_sync_status = {}  # {note_guid: modify_time} modify time is of 'YYYY-MM-DD hh:mm:ss' format
        self.load_note_sync_status_record()

        self.client = None
        self.user_store = None
        self.note_store = None

        self.notebooks = []
        self.notebook_names = {}  # {guid: name,}
        self.notebook_guids = []
        self.notes = {}  # {notebook_guid: [{'guid': note_guid, 'title': note_title}, ...]}

    def dump_note_sync_status_record(self):
        try:
            with open(self.note_sync_status_file_path, 'w') as f:
                text = json.dumps(self.note_sync_status)
                f.write(text)
        except:
            log.error(traceback.format_exc())

    def load_note_sync_status_record(self):
        try:
            with open(self.note_sync_status_file_path) as f:
                text = f.read()
                self.note_sync_status = json.loads(text)
                log.debug('Load sync status succeed')
        except:
            log.error(traceback.format_exc())
            self.note_sync_status = {}

    def update_note_sync_status(self, note_guid, time_str):
        self.note_sync_status[note_guid] = time_str

    def login(self):
    """
    login Evernote
    """
        if self._test:
            return True

        log.debug('Start to login')
        yx = False
        if self.account_type == 'yinxiang':
            yx = True
            log.debug('Account type:' + 'yinxiang')
        else:
            log.debug('Account type:' + 'evernote')

        try:
            self.client = EvernoteClient(token=self.auth_token, sandbox=False, yinxiang=yx)
            self.user_store = self.client.get_user_store()
            version_ok = self.user_store.checkVersion("Evernote EDAMTest (Python)",
                                                      UserStoreConstants.EDAM_VERSION_MAJOR,
                                                      UserStoreConstants.EDAM_VERSION_MINOR)
            if not version_ok:
                log.error('Evernote SDK version not up to data')
                return False
            self.note_store = self.client.get_note_store()
            log.info('Login succeed')
            return True
        except:
            log.debug(traceback.format_exc())
            log.error('Login failed')

    def sync_status(self):
    """
    Sync Evernote status
    """
        if self._test:
            return

        log.debug('Start to sync status.')
        self.notebooks = []
        self.notebook_names = {}
        self.notebook_guids = []
        self.notes = {}
        self.sync_notebook_status()
        self.sync_note_status()
        log.debug('End sync status.')

    def sync_notebook_status(self):
        log.debug('Start to sync notebook status')
        self.notebooks = self.note_store.listNotebooks()
        for notebook in self.notebooks:
            notebook_name = notebook.name.decode('utf-8')
            log.debug(' [notebook] ' + notebook.guid + ':' + notebook_name)
            self.notebook_names[notebook.guid] = notebook_name
            self.notebook_guids.append(notebook.guid)
            self.notes[notebook.guid] = []
        log.debug('End sync notebook status')

    def sync_note_status(self):
        log.debug('Start to sync note status')
        find_filter = NoteStore.NoteFilter()
        spec = NoteStore.NotesMetadataResultSpec()
        spec.includeTitle = True
        spec.includeNotebookGuid = True
        spec.includeUpdated = True
        spec.includeContentLength = True

        got_count = 0
        while True:
            notes = self.note_store.findNotesMetadata(find_filter, got_count, 10000, spec)
            all_count = notes.totalNotes
            got_count += len(notes.notes)

            for note in notes.notes:
                notebook_guid = note.notebookGuid
                if not notebook_guid:
                    continue

                note_title = note.title.decode('utf-8')
                note_modify_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(note.updated/1000)))
                self.note_sync_status[note.guid] = note_modify_time

                if notebook_guid not in self.notes:
                    self.notes[notebook_guid] = []

                self.notes[notebook_guid].append({'guid': note.guid, 'title': note_title})
                log.debug(' [note] ' + note.guid + ':' + note_title + ':' + note_modify_time)

            if got_count >= all_count:
                break
        self.dump_note_sync_status_record()
        log.info('Get all ' + str(got_count) + ' notes ')
        log.debug('End sync note status.')

    def markdown2html(self, markdown_str):
        if not isinstance(markdown_str, unicode):
            log.error('String is not unicode in markdown2html')
            return ''

        html = u'<style>' + self.css_str
        html += '.markdown-body {box-sizing: border-box;min-width: ' \
                '200px;max-width: 980px;margin: 0 auto;padding: 45px;}'
        html += '</style>'
        html += '<article class="markdown-body">'
        md_html = markdown2.markdown(markdown_str, extras=["tables", "fenced-code-blocks", "cuddled-lists"])
        html += md_html
        html += '</article>'

        if log.isEnabledFor(logging.DEBUG):
            pre_html_file_path = os.path.join(self.html_log_path, str(time.time()).replace('.', '') + '-pre_inline.html')
            with open(pre_html_file_path, 'w')as f:
                f.write(html.encode('utf-8-sig'))
                log.debug('Dump html file ' + pre_html_file_path)

        prem = premailer.Premailer(html, preserve_inline_attachments=False, base_path='article')
        html = prem.transform(pretty_print=True)

        if log.isEnabledFor(logging.DEBUG):
            html_file_path = os.path.join(self.html_log_path, str(time.time()).replace('.', '') + '-inline.html')
            with open(html_file_path, 'w')as f:
                f.write(html.encode('utf-8-sig'))
                log.debug('Dump inlined html file ' + html_file_path)

        html = html[html.find('<article'):]
        html = html[html.find('>')+1:]
        html = html[:html.find('</article>')]

        if log.isEnabledFor(logging.DEBUG):
            cut_html_file_path = os.path.join(self.html_log_path, str(time.time()).replace('.', '') + '-cut_inline.html')
            with open(cut_html_file_path, 'w')as f:
                f.write(html.encode('utf-8-sig'))
                log.debug('Dump cutted inlined html file ' + cut_html_file_path)

        log.debug("inline css over")
        return html

    @staticmethod
    def text2html(text_str):
        if not isinstance(text_str, unicode):
            log.error('String is not unicode in markdown2html')
            return ''

        text_str.replace('\r', '')

        html = ''

        lines = text_str.split('\n')
        for line in lines:
            lstr = '<div>'
            if not line:
                lstr += '<br />'
            else:
                lstr += cgi.escape(line)
            lstr += '</div>'
            html += lstr
        return html

    def get_notebook_guid(self, notebook_name):
        for k in self.notebook_names:
            if notebook_name == self.notebook_names[k]:
                return k
        return None

    def is_notebook_exists(self, notebook_name):
        if self.get_notebook_guid(notebook_name):
            return True
        else:
            return False

    def get_note_guid(self, notebook_name, note_title):
        notebook_guid = self.get_notebook_guid(notebook_name)
        if not notebook_guid:
            return None
        for note in self.notes[notebook_guid]:
            if note['title'] == note_title:
                return note['guid']
        return None

    def is_note_exist(self, notebook_name, note_title):
        if self.get_note_guid(notebook_name, note_title):
            return True
        else:
            return False

    def create_notebook(self, notebook_name):
        log.debug('Start to create notebook ' + notebook_name)
        notebook = Types.Notebook()
        if isinstance(notebook_name, unicode):
            notebook.name = notebook_name.encode('utf-8')
        else:
            notebook.name = notebook_name
        notebook.defaultNotebook = False
        created_notebook = self.note_store.createNotebook(notebook)
        log.debug('Create notebook succeed')
        self.notebook_names[created_notebook.guid] = notebook_name
        self.notebook_guids.append(created_notebook.guid)
        self.notes[created_notebook.guid] = []

    def inner_create_note(self, notebook_name, note_title, html, guid=None):
        note = Types.Note()

        if isinstance(note_title, unicode):
            note.title = note_title.encode('utf-8')
        else:
            note.title = note_title

        if guid:
            note.guid = guid
        note.content = '<?xml version="1.0" encoding="UTF-8"?>'
        note.content += '<!DOCTYPE en-note SYSTEM ' \
            '"http://xml.evernote.com/pub/enml2.dtd">'
        note.content += '<en-note>'
        note.content += html
        note.content += '</en-note>'
        if isinstance(note.content, unicode):
            note.content = note.content.encode('utf-8')

        notebook_guid = self.get_notebook_guid(notebook_name)
        if not notebook_guid:
            log.error('In create_note, can not get a notebook named ' + notebook_name)
            return False

        note.notebookGuid = notebook_guid
        return note

    def create_note(self, notebook_name, note_title, html):
        log.debug('Start to create note ' + notebook_name + '/' + note_title)
        note = self.inner_create_note(notebook_name, note_title, html)
        created_note = self.note_store.createNote(note)
        if note.notebookGuid not in self.notes:
            self.notes[note.notebookGuid] = []
        self.notes[note.notebookGuid].append({'guid': created_note.guid, 'title': created_note.title.decode('utf-8')})
        log.debug("Successfully create a new note with GUID %s" % created_note.guid)
        return created_note

    def update_note(self, notebook_name, note_title, html, guid):
        log.debug('Start to update note ' + notebook_name + '/' + note_title)
        note = self.inner_create_note(notebook_name, note_title, html, guid)
        updated_note = self.note_store.updateNote(note)
        log.debug("Successfully update note with GUID: " + updated_note.guid)
        return True

    def sync_file(self, base_path, sub_dir_name, file_name):
        log.debug('Start to sync file ' + os.path.join(base_path, sub_dir_name) + '/' + file_name)
        arr = file_name.split('.')
        if len(arr) != 2 or arr[1] not in ['txt', 'md']:
            return False

        input_file_path = os.path.join(base_path, sub_dir_name) + '/' + file_name
        file_content = ''
        with open(input_file_path) as f:
            file_content = f.read()

        notebook_name = sub_dir_name
        note_title = arr[0]
        note_type = arr[1]

        if not self._test and not self.is_notebook_exists(notebook_name):
            self.create_notebook(notebook_name)

        note_guid = self.get_note_guid(notebook_name, note_title)
        if note_guid and note_guid in self.note_sync_status and self.note_sync_status[note_guid]:
            # Sync only when local_modify_time - last_sync_time > 10 seconds
            if compare(modify_time(input_file_path), self.note_sync_status[note_guid]) < 10:
                log.debug('Skip sync %s : %s' % (notebook_name, note_title))
                return

        if isinstance(file_content, str):
            encoding = 'utf-8'
            if self.input_encoding:
                encoding = self.input_encoding
            else:
                detect_result = chardet.detect(file_content)
                if 'encoding' not in detect_result or not detect_result['encoding']:
                    log.error('Auto detect encoding of file %s failed' % input_file_path)
                    encoding = 'utf-8'
                else:
                    log.debug('Auto detect encoding of file %s succeed: %s' % (input_file_path, detect_result['encoding']))
                    encoding = detect_result['encoding']
            file_content = file_content.decode(encoding)

        html = ''
        if note_type == 'md':
            html = self.markdown2html(file_content)
        else:
            html = self.text2html(file_content)

        if self._test:
            with open('./' + notebook_name + '/' + note_title + '.html', 'w') as f:
                f.write(html.encode('utf-8-sig'))
            return

        try:
            if note_guid:
                self.update_note(notebook_name, note_title, html, note_guid)
            else:
                note_guid = self.create_note(notebook_name, note_title, html).guid
            mod_time = datetime.datetime.now().strftime(TIME_FORMAT)
            self.update_note_sync_status(note_guid, mod_time)
            log.info('Sync %s : %s succeed at %s' % (notebook_name, note_title, mod_time))
        except:
            log.error(traceback.format_exc())

    def sync(self, root_path):  # root_path should be absolute path and unicode string
        sub_dirs = os.listdir(root_path)
        for sub_dir in sub_dirs:
            if '.' in sub_dir or sub_dir in self.ignore_sub_dirs:
                continue
            files = os.listdir(os.path.join(root_path, sub_dir))
            for file in files:
                if '.' not in file or file.split('.')[-1] not in ['md', 'txt']:
                    continue
                self.sync_file(root_path, sub_dir, file)
        self.dump_note_sync_status_record()

    def run(self, root_path, intv_sync_status=1000, intv_sync=100):
        if not self.login():
            log.error('login failed')
            return

        last_sync_status = time.time() - intv_sync_status - 100
        last_sync = time.time() - intv_sync - 10

        while True:
            time.sleep(1)
            cur_time = time.time()
            if cur_time - last_sync_status > intv_sync_status:
                try:
                    self.sync_status()
                except:
                    log.debug(traceback.format_exc())
                    log.error('Sync notebook status failed')
                finally:
                    last_sync_status = cur_time

            cur_time = time.time()
            if cur_time - last_sync > intv_sync:
                self.sync(root_path)
                last_sync = cur_time


if __name__ == '__main__':
    em = EverMark()
    default_workbench = os.path.expanduser(u'~/evermark')
    if not os.path.exists(default_workbench):
        os.mkdir(default_workbench)
    em.run(default_workbench)

