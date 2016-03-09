#!/usr/bin/env python
# coding: utf-8

import os
import cgi
import time
import datetime
import ConfigParser
import chardet

import markdown2
import premailer

import evernote.edam.type.ttypes as Types
import evernote.edam.notestore.NoteStore as NoteStore
import evernote.edam.userstore.constants as UserStoreConstants
from evernote.api.client import EvernoteClient


class EverMark(object):
    def __init__(self, conf='conf.ini'):
        try:
            cf = ConfigParser.SafeConfigParser({'debug': 'no',
                                                'test': 'no',
                                                'account_type': 'evernote',
                                                'root': '.',
                                                'auth_token': '',
                                                'ignore_dirs': '',
                                                'input_encoding': '',
                                                'style': 'github'})
            cf.read(conf)

            opt = cf.get('main', 'debug')
            self._debug = True if (opt == 'yes') else False

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

            self.debug('account_type:' + self.account_type)
            self.debug('root_path:' + self.root_path)
            self.debug('auth_token:' + self.auth_token)
            self.debug('ignore_dirs:' + str(self.ignore_sub_dirs))
            self.debug('style:' + self.style)

        except Exception, e:
            self.debug(str(e))
            print 'ERROR: Read confi.ini failed !'
            exit(0)

        self.css_str = ''
        with open('./css/' + self.style + '.css') as f:
            self.css_str = f.read().decode('utf-8')

        self.client = None
        self.user_store = None
        self.note_store = None

        self.notebooks = []
        self.notebook_names = {}  # {guid: name,}
        self.notebook_guids = []
        self.notes = {}  # {notebook_guid: [{'guid': note_guid, 'title': note_title}, ...]}

    def debug(self, info):
        if self._debug:
            with open('debug.log', 'a') as f:
                time_tag = datetime.datetime.strftime(datetime.datetime.now()-datetime.timedelta(1), '%Y-%m-%d') \
                           + ' ' + time.strftime("%H:%M:%S")
                line = time_tag + ' [DEBUG] %s' % info + '\n'
                f.write(line.encode('utf-8-sig'))
                f.flush()

    def login(self):
        if self._test:
            return True

        self.debug('Start to login.')
        yx = False
        if self.account_type == 'yinxiang':
            yx = True
            self.debug('Account type:' + 'yinxiang')
        else:
            self.debug('Account type:' + 'evernote')

        try:
            self.client = EvernoteClient(token=self.auth_token, sandbox=False, yinxiang=yx)
            self.user_store = self.client.get_user_store()
            version_ok = self.user_store.checkVersion("Evernote EDAMTest (Python)",
                                                      UserStoreConstants.EDAM_VERSION_MAJOR,
                                                      UserStoreConstants.EDAM_VERSION_MINOR)
            if not version_ok:
                print 'ERROR: Evernote SDK version not up to data.'
                return False
            self.note_store = self.client.get_note_store()
            self.debug('Login succeed.')
            return True
        except Exception, e:
            print 'ERROR: Login failed !'
            print e

    def sync_status(self):
        if self._test:
            return

        self.debug('Start to sync status.')
        self.notebooks = []
        self.notebook_names = {}
        self.notebook_guids = []
        self.notes = {}
        self.sync_notebook_status()
        self.sync_note_status()
        self.debug('End sync status.')

    def sync_notebook_status(self):
        self.debug('Start to sync notebook status.')
        self.notebooks = self.note_store.listNotebooks()
        for notebook in self.notebooks:
            notebook_name = notebook.name.decode('utf-8')
            self.debug(' [notebook] ' + notebook.guid + ':' + notebook_name)
            self.notebook_names[notebook.guid] = notebook_name
            self.notebook_guids.append(notebook.guid)
            self.notes[notebook.guid] = []
        self.debug('End sync notebook status.')

    def sync_note_status(self):
        self.debug('Start to sync note status.')
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
                note_title = note.title.decode('utf-8')

                if not notebook_guid:
                    continue

                if notebook_guid not in self.notes:
                    self.notes[notebook_guid] = []

                self.notes[notebook_guid].append({'guid': note.guid, 'title': note_title})

                if self._debug:
                    self.debug(' [note] ' + note.guid + ':' + note_title)

            if got_count >= all_count:
                break

        print 'Get all ', got_count, ' notes .'

        self.debug('End sync note status.')

    def markdown2html(self, markdown_str):
        if not isinstance(markdown_str, unicode):
            print 'ERROR: String is not unicode in markdown2html'
            return ''

        html = u'<style>' + self.css_str
        html += '.markdown-body {box-sizing: border-box;min-width: ' \
                '200px;max-width: 980px;margin: 0 auto;padding: 45px;}'
        html += '</style>'
        html += '<article class="markdown-body">'
        html += markdown2.markdown(markdown_str, extras=["tables", "fenced-code-blocks", "cuddled-lists"])
        html += '</article>'

        prem = premailer.Premailer(html, preserve_inline_attachments=False, base_path='article')
        html = prem.transform(pretty_print=True)
        html = html[html.find('<article'):]
        html = html[html.find('>')+1:]
        html = html[:html.find('</article>')]
        self.debug("inline css over")
        return html

    @staticmethod
    def text2html(text_str):
        if not isinstance(text_str, unicode):
            print 'ERROR: String is not unicode in markdown2html'
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
        self.debug('Start to create notebook ' + notebook_name + ' .')
        notebook = Types.Notebook()
        notebook.name = notebook_name
        notebook.defaultNotebook = False
        created_notebook = self.note_store.createNotebook(notebook)
        self.debug('Create notebook succeed.')
        self.notebook_names[created_notebook.guid] = notebook_name
        self.notebook_guids.append(created_notebook.guid)
        self.notes[created_notebook.guid] = []

    def inner_create_note(self, notebook_name, note_title, html, guid=None):
        note = Types.Note()
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
            print 'ERROR: In create_note, can not get a notebook named ' + notebook_name
            return False

        note.notebookGuid = notebook_guid
        return note

    def create_note(self, notebook_name, note_title, html):
        self.debug('Start to create note ' + notebook_name + '/' + note_title + '  .')
        note = self.inner_create_note(notebook_name, note_title, html)
        created_note = self.note_store.createNote(note)
        self.notes[note.notebookGuid].append({'guid': created_note.guid, 'title': created_note.title})
        self.debug("Successfully create a new note with GUID %s." % created_note.guid)
        return True

    def update_note(self, notebook_name, note_title, html, guid):
        self.debug('Start to update note ' + notebook_name + '/' + note_title + '  .')
        note = self.inner_create_note(notebook_name, note_title, html, guid)
        updated_note = self.note_store.updateNote(note)
        self.debug("Successfully update note with GUID: " + updated_note.guid)
        return True

    def sync_file(self, sub_dir_name, file_name):
        self.debug('Start to sync file ' + os.path.join(self.root_path, sub_dir_name) + '/' + file_name)
        arr = file_name.split('.')
        if len(arr) != 2 or arr[1] not in ['txt', 'md']:
            return False

        input_file_path = os.path.join(self.root_path, sub_dir_name) + '/' + file_name
        file_content = ''
        with open(input_file_path) as f:
            file_content = f.read()

        notebook_name = sub_dir_name
        note_title = arr[0]
        note_type = arr[1]

        if not self._test and not self.is_notebook_exists(notebook_name):
            self.create_notebook(notebook_name)

        if isinstance(file_content, str):
            encoding = 'utf-8'
            if self.input_encoding:
                encoding = self.input_encoding
            else:
                detect_result = chardet.detect(file_content)
                if 'encoding' not in detect_result or not detect_result['encoding']:
                    print 'ERROR: Auto detect encoding of file %s failed.' % input_file_path
                    encoding = 'utf-8'
                else:
                    self.debug('Auto detect encoding of file %s succeed: %s' % (input_file_path, detect_result['encoding']))
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

        note_guid = self.get_note_guid(notebook_name, note_title)
        if note_guid:
            self.update_note(notebook_name, note_title, html, note_guid)
        else:
            self.create_note(notebook_name, note_title, html)

    def sync(self):
        sub_dirs = os.listdir('.')
        for sub_dir in sub_dirs:
            if '.' in sub_dir or sub_dir in self.ignore_sub_dirs:
                continue
            files = os.listdir('./'+sub_dir)
            for file in files:
                if '.' not in file or file.split('.')[-1] not in ['md', 'txt']:
                    continue
                self.sync_file(sub_dir, file)

    def run(self, intv_sync_status=1000, intv_sync=100):
        if not self.login():
            print 'login failed'
            return

        last_sync_status = time.time() - intv_sync_status - 100
        last_sync = time.time() - intv_sync - 10

        while True:
            time.sleep(1)
            cur_time = time.time()
            if cur_time - last_sync_status > intv_sync_status:
                try:
                    self.sync_status()
                except Exception, e:
                    self.debug(str(e))
                    print 'WARN: Sync notebook status failed.'
                finally:
                    last_sync_status = cur_time

            cur_time = time.time()
            if cur_time - last_sync > intv_sync:
                self.sync()
                last_sync = cur_time


if __name__ == '__main__':
    em = EverMark()
    em.run()
