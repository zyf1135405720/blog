#
# import json, urllib
# from urllib import urlencode
#
# url = "http://v.juhe.cn/sms/send"
# params = {
#     "mobile": "13429667914",  # 接受短信的用户手机号码
#     "tpl_id": "111",  # 您申请的短信模板ID，根据实际情况修改
#     "tpl_value": "#code#=1235231",  # 您设置的模板变量，根据实际情况修改
#     "key": "您申请的ApiKey",  # 应用APPKEY(应用详细页查询)
# }
# params = urlencode(params)
# f = urllib.urlopen(url, params)
# content = f.read()
# res = json.loads(content)
# if res:
#     print(res)
# else:
#     print("请求异常")
#
#
#
#
#
#
#
