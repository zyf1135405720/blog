def get_paginator_data(paginator, current_page, around_count=2):
    """
    :param paginator: 分页对象
    :param current_page: 当前页数据
    :param around_count: 显示的页码数
    :return: 当前页码、总页数、左边是否有更多页标记、右边是否有更多标记
    左边页码范围、右边页码范围
    """

    current_page_num = current_page.number
    total_page_num = paginator.num_pages

    left_has_more_page = False
    right_has_more_page = False

    # 计算出左边页码范围
    left_start_index = current_page_num - around_count
    left_end_index = current_page_num
    if left_end_index <= around_count * 2 + 1:
        left_page_range = range(1, left_end_index)
    else:
        left_has_more_page = True
        left_page_range = range(left_start_index, left_end_index)

    # 计算出右边页码范围

    right_start_index = current_page_num + 1
    right_end_index = current_page_num + around_count+1
    if current_page_num >= total_page_num - around_count * 2:
        right_page_range = range(right_start_index, total_page_num + 1)
    else:
        right_has_more_page = True
        right_page_range = range(right_start_index, right_end_index)

    return {
        'current_page_num':current_page_num,
        'total_page_num':total_page_num,
        'left_has_more_page':left_has_more_page,
        'right_has_more_page':right_has_more_page,
        'left_pages':left_page_range,
        'right_pages':right_page_range,
    }




