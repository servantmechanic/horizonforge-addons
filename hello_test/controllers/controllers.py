# from odoo import http


# class HelloTest(http.Controller):
#     @http.route('/hello_test/hello_test', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/hello_test/hello_test/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('hello_test.listing', {
#             'root': '/hello_test/hello_test',
#             'objects': http.request.env['hello_test.hello_test'].search([]),
#         })

#     @http.route('/hello_test/hello_test/objects/<model("hello_test.hello_test"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('hello_test.object', {
#             'object': obj
#         })

