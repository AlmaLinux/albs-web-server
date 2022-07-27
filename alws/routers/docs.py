import os
import re

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse, HTMLResponse
import markdown

from alws.config import settings


public_router = APIRouter(
    prefix='/docs',
    tags=['docs'],
)


@public_router.get('/', response_class=JSONResponse)
async def list_documents():

    def format_article_name(name: str) -> str:
        return re.sub(r'\.md$', '', re.sub(r'-', ' ', name), re.IGNORECASE)

    documents = {}
    doc_path = settings.documentation_path
    if not doc_path or not os.path.exists(doc_path):
        return documents
    for chapter_dir in os.listdir(doc_path):
        chapter_path = os.path.join(doc_path, chapter_dir)
        if not os.path.isdir(chapter_path):
            continue
        articles = []
        for article_file in os.listdir(chapter_path):
            if not article_file.endswith('.md'):
                continue
            article_path = os.path.join(chapter_path, article_file)
            if not os.path.isfile(article_path):
                continue
            articles.append({
                'file': article_file,
                'name': format_article_name(article_file),
            })
        if articles:
            documents[chapter_dir] = articles
    return documents


@public_router.get('/document/{chapter}/{article}')
async def render_document(chapter: str, article: str):
    doc_path = settings.documentation_path
    if not doc_path or not os.path.exists(doc_path):
        return JSONResponse(
            content={
                'message': f'Documentation path="{doc_path}" doesn`t exist',
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    article_path = os.path.join(doc_path, chapter, article)
    if not os.path.exists(article_path):
        return JSONResponse(
            content={
                'message': f'Article="{chapter}/{article}" doesn`t exist'
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    with open(article_path, 'r', encoding='utf-8') as file:
        text = file.read()
    return HTMLResponse(
        content=markdown.markdown(text),
        status_code=status.HTTP_200_OK,
    )
