from flask_restful import Resource
from flask import request
from utils.authorizations import admin_required
from models.user import UserModel
from schemas import UserSchema
from resources.email import Email
import string
import random


class UserInvite(Resource):
    @admin_required
    def post(self):
        data = request.json
        temp_password = "".join(random.choice(string.ascii_lowercase) for i in range(8))
        user = UserModel.create(
            schema=UserSchema, payload={**data, "password": temp_password}
        )
        Email.send_user_invite_msg(user)
        return {"message": "User Invited"}, 201
