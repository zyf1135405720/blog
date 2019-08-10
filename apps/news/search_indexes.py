from haystack import indexes

from news.models import News
from .models import News


class NewsIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    id = indexes.IntegerField(model_attr='id')
    title = indexes.CharField(model_attr='title')
    digest = indexes.CharField(model_attr='digest')
    content = indexes.CharField(model_attr='content')
    image_url = indexes.CharField(model_attr='image_url')

    def get_model(self):
        '''返回简历索引的模型类'''
        return News

    def index_queryset(self, using=None):
        '''返回简历索引的数据查询集'''
        return self.get_model().objects.filter(is_delete=False, tag_id=1)
