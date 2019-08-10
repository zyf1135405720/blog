import json

from django.contrib.auth import login, logout
from django.shortcuts import render, redirect
from django.urls import reverse

from django.views import View

from users.forms import RegisterForm, LoginForm,RetrieveForm
from users.models import Users
from utils.json_fun import to_json_data
from utils.res_code import Code, error_map


# 基于函数或者基于类的视图
# 接受的参数第一个必须为request，并且需要返回一个response对象
class RegisterView(View):
    def get(self, request):
        return render(request, 'users/register.html')

    def post(self, request):
        '''
        register
        /users/register/
        1.接收前端json参数
        2.校验参数
        3.写入数据库
        4.返回json数据到前端
        :param request:
        :return:
        '''
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))
        form = RegisterForm(data=dict_data)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            mobile = form.cleaned_data.get('mobile')
            user = Users.objects.create_user(username=username, password=password, mobile=mobile)
            login(request, user)
            return to_json_data(errmsg='恭喜您,注册成功!')

        else:
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class LoginView(View):
    def get(self, request):
        return render(request, 'users/login.html')

    def post(self, request):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))
        form = LoginForm(data=dict_data, request=request)
        if form.is_valid():
            return to_json_data(errmsg='恭喜您,登陆成功')
        else:
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)  # 拼接错误信息为一个字符串

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect(reverse('users:login'))


class RetrieveView(View):

    def get(self,request):
        return render(request,'users/retrieve.html')

    def post(self,request):
        json_data = request.body
        if not json_data:
            return to_json_data(errno=Code.PARAMERR, errmsg=error_map[Code.PARAMERR])
        dict_data = json.loads(json_data.decode('utf8'))
        form = RetrieveForm(data=dict_data)
        if form.is_valid():
            username=form.cleaned_data.get('username')
            password=form.cleaned_data.get('password')
            user=Users.objects.filter(username=username).first()
            user.set_password(password)
            user.save()
            return to_json_data(errmsg='恭喜您修改密码成功')

        else:
            err_msg_list = []
            for item in form.errors.get_json_data().values():
                err_msg_list.append(item[0].get('message'))
            err_msg_str = '/'.join(err_msg_list)

            return to_json_data(errno=Code.PARAMERR, errmsg=err_msg_str)



