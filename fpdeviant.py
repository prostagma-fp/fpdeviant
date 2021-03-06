import deviantart
import shutil
import requests
import os, re
from html import unescape
from time import gmtime, strftime

# Monkey patching because library is missing filename in a def, and mature on another
def download_deviation_with_filename(self, deviationid):
    response = self._req('/deviation/download/{}'.format(deviationid))
    return {
        'src' : response['src'],
        'filename' : response['filename']
    }
deviantart.Api.download_deviation = lambda self, deviationid: download_deviation_with_filename(self, deviationid)

def get_gallery_folder(self, username="", folderid="", mode="popular", offset=0, limit=10):

        """Fetch gallery folder contents

        :param username: The user to query, defaults to current user
        :param folderid: UUID of the folder to list, if omitted query ALL folders
        :param mode: Sort results by either newest or popular
        :param offset: the pagination offset
        :param limit: the pagination limit
        """

        if not username and self.standard_grant_type == "authorization_code":
            response = self._req('/gallery/{}'.format(folderid), {
                "mode":mode,
                "offset":offset,
                "limit":limit
            })
        else:
            if not username:
                raise DeviantartError("No username defined.")
            else:
                response = self._req('/gallery/{}'.format(folderid), {
                    "username":username,
                    "mode":mode,
                    "offset":offset,
                    "limit":limit,
                    "mature_content":"true"
                })

        deviations = []

        for item in response['results']:
            d = deviantart.deviation.Deviation()
            d.from_dict(item)
            deviations.append(d)

        if "name" in response:
            name = response['name']
        else:
            name = None

        return {
            "results" : deviations,
            "name" : name,
            "has_more" : response['has_more'],
            "next_offset" : response['next_offset']
        }
deviantart.Api.get_gallery_folder = lambda self, username, folderid, offset, limit, mode="popular": get_gallery_folder(self, username, folderid, mode, offset, limit)

# End monkey patching

DA_CLIENT = None
SHORT_PATH = 'Working/da_'

class InvalidRequestError(ValueError):
    """An error caused when attempting a web request."""
    pass
class InvalidParse(ValueError):
    """An error caused when attempting to parse a fetched file."""
    pass
class InvalidFileError(OSError):
    """An error caused when attempting to read or write to a file that isn't a file (e.g., a directory)."""
    pass

def delete_folder(uuid):
    """Deletes folder path defined by SHORT_PATH + :uuid:"""
    try: shutil.rmtree(SHORT_PATH+uuid)
    except: pass

def setup_client_from_file(dafilename):
    """Creates a DeviantArt API connection from a text file.
    File must be built as (ID=[client_id]\\nSECRET=[client_secret])"""

    # Get client's id and secret
    try:
        with open(dafilename, 'r') as da_file:
            try:
                line = da_file.readline()
                da_id = line[3:-1]
                line = da_file.readline()
                da_secret = line[7:39]
            except: raise InvalidParse(dafilename +' is missing one more parameters (ID=[client_id]\\nSECRET=[client_secret]).')
    except: raise InvalidFileError(dafilename + ' could not be accessed.')

    # Connect to DeviantArt
    try: da = deviantart.Api(da_id, da_secret)
    except: raise InvalidRequestError('Could not setup API.')

    return da

def get_da_curation(deviationurl=None, deviationdata=None):

    """Creates a Flashpoint curation from a DeviantArt link. Returns the deviation's UUID if succeeds.

    :param deviationurl: The deviation link you want to curate from.
    :param deviationdata: The deviation data from gallery/{folderid} you want to curate from.
    """

    # Aborts if both url and data are abscent
    if not deviationurl and not deviationdata:
        print('You must pass the deviation\'s url or UUID.')
        return

    # Fetch website and get UUID if deviationdata is empty
    if not deviationdata:
        # username.deviantart.com/art/example -> deviantart.com/username/art/example
        deviationurl = re.sub(r'www\.((.+)\.)deviantart\.com', r'www.deviantart.com/\2', re.sub(r'^(https?://)?(www\.)?(\w)', r'https://www.\3', deviationurl))
        try: html_content = requests.get(deviationurl).text
        except:
            print('"' + deviationurl + '" could not be obtained.')
            return

        try:
            id_index = html_content.find('DeviantArt://deviation/')+23
            uuid = html_content[id_index:id_index+36]
        except:
            print('"' + deviationurl + '" is not a valid deviation.')
            return

        if ('\n' in uuid):
            print('"' + deviationurl + '" has no valid UUID.')
            return
    else:
        uuid = deviationdata.deviationid

    # Source
    source_url = deviationurl if deviationurl else deviationdata.url

    # Get download link; abort if not downloadable
    try:
        swfurl = DA_CLIENT.download_deviation(uuid)
    except:
        print(source_url + ': Work is not downloadable. UUID '+ uuid)
        return

    # Get deviation meta, devationdata does not have desc
    try:
        metadata = DA_CLIENT.get_deviation_metadata(uuid)[0]
    except:
        print(source_url + ': Metadata could not be downloaded.')
        return

    # Download files, abort if not flash
    if swfurl['filename'].endswith('.swf'):
        download_path = SHORT_PATH + uuid + '/content/api-da.wixmp.com/_api/download/'
        
        # Create folders and abort if they already exist
        try: os.makedirs(download_path)
        except:
            print(source_url + ': Error creating folder structure (curation may already exist).')
            return
        
        # Download file
        try:
            with open(download_path + swfurl['filename'], 'wb') as dump_it:
                myswf = requests.get(swfurl['src'], stream=True)
                myswf.raw.decode_content = True
                shutil.copyfileobj(myswf.raw, dump_it)
        except:
            print('"' + deviationurl + '"\'s file failed to be downloaded.')
            delete_folder(uuid)
            return

        # Find release date and description
        if not deviationdata:
            date_index = html_content.find(' dateTime="')+11
            releaseDate = html_content[date_index:date_index+10]
        else: releaseDate = strftime("%Y-%m-%d", gmtime(int(deviationdata.published_time)))

        originalDescription = metadata['description']
        replacements = [
            (r'<a(.+?)href="(https:..www.deviantart.com.users.outgoing\?)?(.+?)"(.+?)>',  r'\3'),
            (r'<img (.+?)alt="(.+?)"(.+?)\/>',  r'\2'),
            (r'\s?<br(\s\/)?>', '\n'),
            (r'\s?&nbsp;\s?', ''),
            (r'\n?(<ul>)?<li>', '\n??? '),
            (r'<\/?(.+?)>', ''),
            (r'\s?\n\n\n\s?', '\n\n')
        ]
        for old, new in replacements:
            originalDescription = re.sub(old, new, originalDescription)
        originalDescription = unescape(originalDescription).strip('\n').strip().replace('\n', '\n  ')
        
        # Grab logo
        try:
            if not deviationdata: logo_link = re.search(r'(?<=rel=\"preload\" href=\")https:..images-wixmp(.+?)(?=\")', html_content).group(0)
            else: logo_link = deviationdata.preview['src']       
            
            with open(SHORT_PATH + uuid + '/logo.png', 'wb') as f_image:
                myimg = requests.get(logo_link, stream=True)
                f_image.write(myimg.content)
        except: pass

        # Create YAML
        try: 
            with open(SHORT_PATH + uuid + '/meta.yaml', 'w', encoding='utf-8') as yaml:
                content = """Title: "{}"
Alternate Titles: null
Library: arcade
Series: null
Developer: "{}"
Publisher: DeviantArt
Play Mode: Single Player
Release Date: {}
Version: null
Languages: en
Extreme: null
Tags: null
Source: {}
Platform: Flash
Status: Playable
Application Path: FPSoftware\\Flash\\flashplayer_32_sa.exe
Launch Command: {}
Game Notes: null
Original Description: |-\n  {}
Curation Notes: null
Mount Parameters: null
Additional Applications: {{}} """.format(metadata['title'].replace('"', '\"'), str(metadata['author']).replace('"', '\"'), releaseDate, source_url, 'http://api-da.wixmp.com/_api/download/'+swfurl['filename'], originalDescription)
                yaml.write(content)
        except:
            print(source_url + ': Error creating metadata file.')
            delete_folder(uuid)
            return

        # All done!
        print(source_url + ': Success')
        return uuid

    else:
        print(source_url + ' is not a Flash deviation.')
        return

def get_collection_id(collectionurl):
    try: html_content = requests.get(collectionurl).text
    except:
        print(collectionurl + ': collection could not be fetched.')
        return
    try:
        return re.search(r'DeviantArt:\/\/collection\/[\w-].+\/([\w-].+)"', html_content).group(1)
    except:
        print(collectionurl + ': failed to get collection ID.')
        return

def check_da_url(devianturl):

    """Checks if a link is a single deviation or a group (galleries, favorites or username link) for get_da_curation(). Scraps can only be fetched individually.

    :param deviationurl: The deviation link you want to curate from.
    """
    curationcounter = 0
    offset = 0
    if re.fullmatch(r'https?:..www.deviantart.com\/([\w-]+?)($|\/)(gallery(\/.*)?)?', devianturl):
        folder_id = ''
        if re.fullmatch(r'https?:..www.deviantart.com\/([\w-]+?)\/gallery\/[\dA-Z].*', devianturl): # Specific gallery
            try:
                html_content = requests.get(devianturl).text
                folder_id = re.search(r'DeviantArt:\/\/gallery\/[\w-].+\/([\dA-Z].+)"', html_content).group(1)
            except: pass

        while offset != -1:
            gallery = DA_CLIENT.get_gallery_folder(re.search(r'https?:..www.deviantart.com.(.+?)($|\/)', devianturl).group(1), folderid=folder_id, offset=offset, limit=24)
            for deviation in gallery['results']:
                if(get_da_curation(deviationdata=deviation)):
                    curationcounter += 1
            offset += 24
            if gallery['has_more'] == False: offset = -1

        if folder_id == '': print('Note: scraps (if any) can only be fetched individually.')

    elif re.fullmatch(r'https?:..www.deviantart.com\/([\w-]+?)\/favourites\/(\d+?)\/([\w-]+?)$', devianturl):
        id = get_collection_id(devianturl)
        while offset != -1:
            collection = DA_CLIENT.get_collection(id, re.search(r'https?:..www.deviantart.com\/(.+?)\/', devianturl).group(1), offset=offset, limit=24)
            for deviation in collection['results']:
                if(get_da_curation(deviationdata=deviation)):
                    curationcounter += 1
            offset += 24
            if collection['has_more'] == False: offset = -1
    else: #Regular submission link
        if get_da_curation(devianturl):
            curationcounter += 1

    return curationcounter

def return_msg(value):
    if value <= 0:
        print('\nFailed to download file(s). Press Enter to exit this program.')
    else:
        if value == 1:
            print('\nFinished! Press Enter to exit this program.')
        else:
            print('\n{} files curated! Press Enter to exit this program.'.format(value))


def looping_menu():
    print('fpdeviant by prostagma-fp --- version 1.1.4 --- 2021-10-12')
    print('Supports deviation, favourites, gallery and user URLs')
    value = input('Enter a filename or URL: ')
    while value != '':
        if value.startswith('http'):
            print('Fetching file...')
            return_msg(check_da_url(value))
        else:
            try:
                with open(value, 'r') as d_file:
                    print('asas')
                    totalchanges = 0
                    for line in d_file:
                        print('trim time')
                        line = line.strip('\r\n\n')
                        print('Fetching '+line+'...\n')
                        totalchanges += check_da_url(line)
                return_msg(totalchanges)
            except:
                print('Error: Could not read file. Press Enter to exit this program.')
        value = input('Or type another filename or URL: ')

if __name__ == "__main__":
    DA_CLIENT = setup_client_from_file('deviantart.txt')
    if DA_CLIENT:
        looping_menu()
    else:
        print('You must enter a DeviantArt client ID and secret in deviantart.txt first.')
        
