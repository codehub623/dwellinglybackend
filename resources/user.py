from flask_restful import Resource, reqparse

from models.property import PropertyModel
from models.tenant import TenantModel
from resources.admin_required import admin_required
from models.user import UserModel, RoleEnum
from models.revoked_tokens import RevokedTokensModel
import json
from werkzeug.security import safe_str_cmp
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_claims, get_raw_jwt, get_jwt_identity, jwt_refresh_token_required
import bcrypt


class UserRoles(Resource):
    def get(self):
        roles = {}
        for role in RoleEnum:
            roles[role.name] = role.value
        result = json.dumps(roles)
        return result, 200

class UserRegister(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('firstName',type=str,required=True,help="This field cannot be blank.")
    parser.add_argument('lastName',type=str,required=True,help="This field cannot be blank.")
    parser.add_argument('email',type=str,required=True,help="This field cannot be blank.")
    parser.add_argument('password', type=str, required=True, help="This field cannot be blank.")
    parser.add_argument('role',type=int,required=False,help="This field is not required.")
    parser.add_argument('archived',type=str,required=False,help="This field is not required.")
    parser.add_argument('phone',type=str,required=True,help="This field cannot be blank.")

    def post(self):
        data = UserRegister.parser.parse_args()

        # I think the above print statement will ALWAYS be false because upon saving - we're always hashing
        # So we're NEVER seeing the plaintext password anymore
        # I think there was a lot of learning here...but ultimately...we're not doing it right
        # When we register
        # We need to take the plain text password
        # hash that
        # store it in the db
        # then when we login -
        # we need to take that same plain text password
        # hash it again --> don't think this needs to happen - because checkpw function can make the comparison
        # then compare it to the db
        # start here when you come back

        # Let's start by hashing the password
        # We'll convert the string into bytes for bcrypt to be able to process
        hashed_password = bcrypt.hashpw(bytes(data['password'], 'utf-8'), bcrypt.gensalt())

        if UserModel.find_by_email(data['email']):
            return {"message": "A user with that email already exists"}, 400

        user = UserModel(firstName=data['firstName'],
                         lastName=data['lastName'], email=data['email'],
                         password=hashed_password, phone=data['phone'],
                         role=RoleEnum(data['role']) if data['role'] else None, archived=data['archived'])
        # And we'll store it into the db as bytes
        user.save_to_db()

        return {"message": "User created successfully."}, 201

class User(Resource):
    @admin_required
    def get(self, user_id):
        user = UserModel.find_by_id(user_id)

        if not user:
            return {'message': 'User Not Found'}, 404

        user_info = user.json()

        if user.role == RoleEnum.PROPERTY_MANAGER:
            user_info['properties'], tenant_list = zip(*((p.json(), p.tenants) for p in PropertyModel.find_by_manager(user_id) if p))
            
            tenant_IDs = [tenant.id for sublist in tenant_list for tenant in sublist]
            tenants_list = [TenantModel.find_by_id(t) for t in set(tenant_IDs)]
            user_info['tenants'] = [t.json() for t in tenants_list if t]

        return user_info, 200

    @jwt_required
    def patch(self,user_id):


        user = UserModel.find_by_id(user_id)


        parser = reqparse.RequestParser()
        parser.add_argument('role', type=int, required=False, help="This field is not required.")
        parser.add_argument('firstName',type=str, required=False, help="This field is not required.")
        parser.add_argument('lastName',type=str, required=False, help="This field is not required.")
        parser.add_argument('email',type=str, required=False, help="This field is not required.")
        parser.add_argument('phone',type=str, required=False,help="This field is not required.")
        parser.add_argument('password',type=str, required=False,help="This field is not required.")

        data = parser.parse_args()

        if not user:
            return {"Message": "Unable to find user."}, 400
      
        if user_id != get_jwt_identity() and not get_jwt_claims()['is_admin']:
            return {"Message": "You cannot change another user's information unless you are an admin"}, 403

        if data['role'] and not get_jwt_claims()['is_admin']:
            return {"Message": "Only admins can change roles"}, 403

        if data['role']:
          user.role = RoleEnum(data['role'])
        if (data['firstName'] != None):
            user.firstName = data['firstName']
        if (data['lastName'] != None):
            user.lastName = data['lastName']
        if data['email']:
            user.email = data['email']
        if data['phone']:
            user.phone = data['phone']
        if data['password']:
            user.password = data['password']

        try:
            user.save_to_db()
        except:
            return {'Message': 'An Error Has Occurred. Note that you can only update a user\'s role, email, phone, or password.'}, 500


        if user_id == get_jwt_identity():
            new_tokens = {
                "access_token": create_access_token(identity=user.id, fresh=True),
                "refresh_token": create_refresh_token(user.id)
            }
            user.update_last_active()
            return {**user.json(), **new_tokens}, 201

        return user.json(), 201

    @admin_required
    def delete(self, user_id):
        user = UserModel.find_by_id(user_id)
        if not user:
            return {"Message": "Unable to delete User"}, 400
        user.delete_from_db()
        return {"Message": "User deleted"}, 200

class ArchiveUser(Resource):

    @admin_required
    def post(self, user_id):
        user = UserModel.find_by_id(user_id)
        if(not user):
            return{'Message': 'User cannot be archived'}, 400

        user.archived = not user.archived
        try:
            user.save_to_db()
        except:
            return {'Message': 'An Error Has Occured'}, 500

        if user.archived:
            # invalidate access token
            jti = get_raw_jwt()['jti']
            revokedToken = RevokedTokensModel(jti=jti)
            revokedToken.save_to_db()

        return user.json(), 201

class UserLogin(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('email',type=str,required=True,help="This field cannot be blank.")
    parser.add_argument('password', type=str, required=True, help="This field cannot be blank.")

    def post(self):
        print('IN THE POST ENDPOINT')
        data = UserLogin.parser.parse_args()

        user = UserModel.find_by_email(data['email'])

        if user and user.archived:
            return {"message": "Not a valid user"}, 403

        # Now we need to login and compare the plaintext pw which is a string to the hashed pw
        print('Passwords to compare: ')
        print('Plain-text: ')
        print(data['password'])
        print('Hashed-password: ')
        print(user.password)
        print(bcrypt.checkpw(bytes(data['password'], 'utf-8'), user.password))
        if user and bcrypt.checkpw(bytes(data['password'], 'utf-8'), user.password):
            access_token = create_access_token(identity=user.id, fresh=True) 
            refresh_token = create_refresh_token(user.id)
            user.update_last_active()
            return {
                'access_token': access_token,
                'refresh_token': refresh_token
            }, 200

        return {"message": "Invalid Credentials!"}, 401       

class UsersRole(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('userrole',type=int,required=True,help="This field cannot be blank.")
    parser.add_argument('name',type=str,required=False)

    @admin_required
    def post(self):
        data = UsersRole.parser.parse_args()
        if data["name"]:
            users = UserModel.find_by_role_and_name(RoleEnum(data['userrole']), data['name'])
        else:
            users = UserModel.find_by_role(RoleEnum(data['userrole']))
        users_info = []
        for user in users:
            info = user.json()
            info['properties'] = [p.json() for p in PropertyModel.find_by_manager(user.id) if p]
            users_info.append(info)
        return {'users': users_info}

# This endpoint allows the app to use a refresh token to get a new access token 
class UserAccessRefresh(Resource):
    
    # The jwt_refresh_token_required decorator insures a valid refresh
    # token is present in the request before calling this endpoint. We
    # can use the get_jwt_identity() function to get the identity of
    # the refresh token, and use the create_access_token() function again
    # to make a new access token for this identity.
    @jwt_refresh_token_required
    def post(self):
        current_user = get_jwt_identity()
        ret = {
            'access_token': create_access_token(identity=current_user)
        }
        return ret, 200
