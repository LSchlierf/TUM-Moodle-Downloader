import asyncio
import datetime
import os
import urllib

from bs4 import BeautifulSoup
from dateutil.parser import parse as parsedate

import globals


def background(f):
    def wrapped(*args):
        return asyncio.get_event_loop().run_in_executor(None, f, *args)

    return wrapped


class Resource:
    def __init__(self, resource_div, is_recent):
        self.resource_div = resource_div
        self.is_recent = is_recent
        self.name = Resource.get_resource_name(self.resource_div)
        self.resource_url = Resource.get_resource_url(self.resource_div)
        if self.resource_url is None:
            self.available = False
        else:
            # TODO: validate url to check, if it is available
            self.available = True
        self.type = self.get_resource_type(self.resource_div)

    @staticmethod
    def get_resource_name(resource_div):
        name = resource_div.find('span', class_='instancename')
        if name:
            return name.contents[0].strip()
        return resource_div.find('span', class_='fp-filename').contents[0].strip()

    @staticmethod
    def get_resource_url(resource_div):
        resource_url_anchor = resource_div.find('a')
        if resource_url_anchor is None:
            return None
        else:
            return resource_url_anchor.get('href', None)

    @staticmethod
    def get_resource_type(resource_div):
        resource_type_span = (resource_div.find('span', class_="accesshide"))
        if resource_type_span is None:
            return 'other (e.g. quiz, forum, ...)'

        resource_type = ("" + resource_type_span.contents[0]).strip()
        if ['Datei', 'File'].__contains__(resource_type):
            return 'file'
        elif ['Ordner', 'Folder', 'Verzeichnis'].__contains__(resource_type):
            return 'folder'
        elif ['Aufgabe', 'Assignment'].__contains__(resource_type):
            return 'assignment'
        elif ['LINK/URL', 'URL'].__contains__(resource_type):
            # TODO what to do with other types?
            if 'pdf' in resource_div.find('img')['src']:
                return 'url'
        return 'other (e.g. quiz, forum, ...)'

    @staticmethod
    def _download_file(url, destination_dir, update_handling):
        # Extract header information of the file before actually downloading it
        # Redirects MUST be enabled otherwise this won't work for files which are to be downloaded directly from the
        # course's home page (--> example: redirect from https://www.moodle.tum.de/mod/resource/view.php?id=831037
        # to https://www.moodle.tum.de/pluginfile.php/1702929/mod_resource/content/1/%C3%9Cbung%202_L%C3%B6sung.pdf)
        file_head = globals.global_session.head(url, allow_redirects=True)

        # Use 'file_head.headers' to access the files headers. Interesting headers include:
        # - 'Content-Length'
        # --> TODO: consider asking for the user's consent before downloading a huge file
        # - 'Content-Type'

        file_url = file_head.url
        if "/view.php" in file_url:
            file_head = globals.global_session.head(url + '&redirect=1', allow_redirects=True)
            file_url = file_head.url
            if "/view.php" in file_url:
                return
        # Decode encoded URL (for more info see: https://www.urldecoder.io/python/) to get rid of "percent encoding"
        # (as in https://www.moodle.tum.de/pluginfile.php/1702929/mod_resource/content/1/%C3%9Cbung%202_L%C3%B6sung.pdf)
        decoded_file_url = urllib.parse.unquote(file_url)

        # Extract file name from URL
        filename = os.path.basename(decoded_file_url)
        if '?forcedownload=1' in filename:
            filename = filename.replace('?forcedownload=1', '')

        destination_path = os.path.join(destination_dir, filename)

        # Apply update handling in case the file already exists
        file_exists = os.path.exists(destination_path)
        if file_exists and update_handling != "replace":
            if update_handling == "skip":
                print(f"Skipping file \u001B[35m{filename}\u001B[0m because it already exists at {destination_path}")
                return
            if update_handling == "add":
                # Create filename "filename (i).extension" and add it as a new version of the file
                i = 1
                (root, ext) = os.path.splitext(filename)
                while file_exists:
                    destination_path = os.path.join(destination_dir, root + ' (' + str(i) + ')' + ext)
                    i += 1
                    file_exists = os.path.exists(destination_path)
            if update_handling == "update":
                url_time = file_head.headers['last-modified']
                url_date = parsedate(url_time).astimezone()
                file_time = datetime.datetime.fromtimestamp(os.path.getmtime(destination_path)).astimezone()
                if url_date <= file_time:
                    print(f"\u001B[33mSkipping\u001B[0m downloaded file: {filename}")
                    return

        print(f'\u001B[32mDownloading\u001B[0m file:         {filename}')
        file = globals.global_session.get(file_url)
        with open(destination_path, 'wb') as f:
            f.write(file.content)
        print('Done. Saved to:           ' + destination_path)

    @staticmethod
    def _download_folder(file_url, destination_path, update_handling):
        folder_soup = BeautifulSoup(globals.global_session.get(file_url).content, 'html.parser')  # Get folder page
        dir_name = folder_soup.find('div', role='main').find('h2')  # Find folder title
        if dir_name:
            dir_name = dir_name.contents[0]
        else:
            dir_name = folder_soup.find('div', class_='page-header-headings').find('h1', class_='h2').contents[0].strip()
        print(f'Downloading folder: \u001B[34m{dir_name}\u001B[0m')
        folder_path = os.path.join(destination_path, dir_name)
        if not os.path.exists(folder_path):
            print(f'\u001B[32mCreating\u001B[0m directory: {dir_name}')
            os.mkdir(folder_path)
        files = folder_soup.find_all('span', class_='fp-filename')  # Finds all files in folder page
        for file in files:
            if len(file.contents) < 3: # <3
                continue
            file_url = file.contents[1]['href']
            print('\t', end='')
            Resource._download_file(file_url, folder_path, update_handling)

    @staticmethod
    def _download_folder_page(file_url, destination_path, update_handling):
        folder_soup = BeautifulSoup(globals.global_session.get(file_url).content, 'html.parser')  # Get folder page
        files = folder_soup.find_all('span', class_='fp-filename')  # Finds all files in folder page
        for file in files:
            if len(file.contents) < 1:
                continue
            file_url = file.parent['href']
            Resource._download_file(file_url, destination_path, update_handling)

    @staticmethod
    def _download_assignment(file_url, destination_path, update_handling):
        # print('Extracting files from assignment')
        # Get assignment page
        assignment_soup = BeautifulSoup(globals.global_session.get(file_url).content, 'html.parser')
        intro = assignment_soup.find('div', id='intro')
        if intro is None:
            # print('No file found')
            return
        file_anchors = intro.findAll('div', class_='fileuploadsubmission')
        if len(file_anchors) == 0:
            # print('No file found')
            return
        for file_anchor in file_anchors:
            file_url = file_anchor.find('a')['href']
            Resource._download_file(file_url, destination_path, update_handling)

    @staticmethod
    def _is_file(url):
        file_head = globals.global_session.head(url, allow_redirects=True)
        return '.pdf' in file_head.url

    @background
    def download_parallel(self, destination_dir, update_handling):
        Resource.download(self, destination_dir, update_handling)

    def download(self, destination_dir, update_handling):
        if not os.path.exists(destination_dir):
            print(destination_dir + ' not found. Creating path: ' + destination_dir)
            try:
                # Create path (recursively)
                os.makedirs(destination_dir)
            except FileNotFoundError:
                print(f'Could not create path {destination_dir}. Please check the path and try again.')
                return
        # TODO: check, check if resource is actually available for the user
        #  (see: https://github.com/NewLordVile/tum-moodle-downloader/issues/11)
        if self.type == 'file' or self.type == 'url':
            Resource._download_file(self.resource_url, destination_dir, update_handling)
        elif self.type == 'folder':
            Resource._download_folder(self.resource_url, destination_dir, update_handling)
        elif self.type == 'assignment':
            Resource._download_assignment(self.resource_url, destination_dir, update_handling)
        elif Resource._is_file(self.resource_url):
            try:
                Resource._download_file(self.resource_url, destination_dir, update_handling)
            except Exception:
                pass
        else:
            Resource._download_folder_page(self.resource_url, destination_dir, update_handling)