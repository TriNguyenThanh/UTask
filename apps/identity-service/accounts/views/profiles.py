from dj_rest_auth.views import UserDetailsView


class CurrentUserView(UserDetailsView):
    http_method_names = ["get", "head", "options"]
    success_messages = {"GET": "Lấy thông tin hồ sơ cá nhân thành công."}
