from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class IdentityPagePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100

    def get_paginated_response_schema(self, schema):
        return schema

    def get_paginated_response(self, data):
        response = Response(data)
        response.identity_meta = {
            "page": self.page.number,
            "limit": self.page.paginator.per_page,
            "total_count": self.page.paginator.count,
            "total_pages": self.page.paginator.num_pages,
            "has_next": self.page.has_next(),
            "next_cursor": None,
        }
        return response
