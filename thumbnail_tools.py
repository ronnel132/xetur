from bs4 import BeautifulSoup
import re
import requests

class ThumbnailFetcher:
    imgtypes = ['.jpg', '.gif', '.png']
    def fetch_thumbnail(self, post_id, url):
        url = self.__cleanurl(url)
        website = re.match(r'http://(.*)\.com.*', url).group(1)   
        getrequest = requests.get(url)
        soup = BeautifulSoup(getrequest.text)
        if url[-3:] in imgtypes:
            pass
        return { 'imgur' : self.__imgur_thumbnail(soup, post_id),
                'youtube' : self.__youtube_thumbnail(soup, post_id),
                'quickmeme' : self.__quickmeme_thumbnail(soup, post_id)
                }.get(website, False)
    def __cleanurl(self, url):
        return ('http://' + url) if 'http://' not in url else url
    def __imgur_thumbnail(soup, post_id):
        for imgtype in imgtypes:
            if imgtype in 
    def __youtube_thumbnail(soup, post_id):
        pass
    def __quickmeme_thumbnail(soup, post_id):
        pass
    def __get_img_from_src(src):
        pass
        
