from bs4 import BeautifulSoup
import os
import sys
import requests

from convert_to_epub import to_epub
from get_text_from_html import get_chapter_data


# send the link to first page

origin_url = "https://freewebnovel.com"

from bs4 import BeautifulSoup

def get_chapter_metadata(url):

    html = requests.get(url)

    soup = BeautifulSoup(html.content, "html.parser")

    # Title
    title = soup.select_one("h1.tit").text.strip()

    # Author
    author = soup.select_one(".glyphicon-user + .right a").text.strip()

    # Genres
    genres = [a.text.strip() for a in soup.select(".glyphicon-th-list + .right a")]

    # Language
    language = soup.select_one(".glyphicon-globe + .right a").text.strip()

    # Status
    status = soup.select_one(".glyphicon-time + .right").text.strip()

    # Image URL
    img_path = soup.select_one(".m-book1 img")["src"]
    image_url = origin_url + img_path

    # Synopsis / Summary
    synopsis = " ".join(p.text.strip() for p in soup.select(".m-desc .txt .inner p"))

    # Read First link
    read_first_path = soup.select_one(f'a[title^="Read {title} Online Free"]')["href"]
    read_first_url = origin_url + read_first_path

    filename = "media\\image " + title + ".jpeg"
    

    response = requests.get(image_url)

    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
    else:
        print(f"Failed to download image. Status code: {response.status_code}")


    print(f"\n>>> Got the metadata for {title} by: {author}\n")
    # Final dictionary
    book_data = {
        "title": title,
        "author": author,
        "genres": genres,
        "language": language,
        "status": status,
        "image_url": image_url,
        "synopsis": synopsis,
        "starting_url": read_first_url,
        "image_path": filename
    }
    return book_data




def get_chapters(read_first_url):
    count = 0
    chapter_title_list = []
    chapter_text_list = []
    if count == 0:
            next_url = read_first_url

    while next_url:
        current_url = next_url
    
        next_url_short, chapter_title, chapter_data = get_chapter_data(current_url)

        chapter_title_list.append(chapter_title)
        chapter_text_list.append(chapter_data)

        if next_url_short:
             next_url = origin_url +next_url_short
        else:
             next_url = None


    else:
        data = {
             'title': chapter_title_list,
             'text': chapter_text_list
        }
    
    return data

    
