from motor.motor_asyncio import AsyncIOMotorClient
from bot.config.settings import settings


class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        self.client = AsyncIOMotorClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGO_DB]
        await self._create_indexes()
        await self.reset_current_deployments()

    async def _create_indexes(self):
        await self.db.users.create_index("user_id", unique=True)
        await self.db.deployments.create_index("deployment_id", unique=True)
        await self.db.railway_tokens.create_index("token", unique=True)
        await self.db.force_subs.create_index("channel_id", unique=True)
        await self.db.plans.create_index("plan_id", unique=True)
        await self.db.wallet.create_index("user_id", unique=True)
        await self.db.referrals.create_index("user_id", unique=True)

    async def close(self):
        if self.client:
            self.client.close()

    # ---- User Operations ----
    async def get_user(self, user_id: int):
        return await self.db.users.find_one({"user_id": user_id})

    async def create_user(self, user_id: int, username: str = "", full_name: str = "", referred_by: int = None):
        user = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "plan": "free",
            "plan_expiry": None,
            "deployments_count": 0,
            "total_deployments": 0,
            "joined_at": __import__("datetime").datetime.utcnow(),
            "is_banned": False,
            "ban_reason": "",
            "referred_by": referred_by,
            "balance": 0,
            "points": 0,
            "language": "en",
            "notifications": True,
        }
        await self.db.users.insert_one(user)
        return user

    async def update_user(self, user_id: int, data: dict):
        await self.db.users.update_one({"user_id": user_id}, {"$set": data})

    async def get_all_users(self):
        return await self.db.users.find({}).to_list(None)

    async def count_users(self):
        return await self.db.users.count_documents({})

    # ---- Deployment Operations ----
    async def create_deployment(self, data: dict):
        await self.db.deployments.insert_one(data)
        return data

    async def get_deployment(self, deployment_id: str):
        return await self.db.deployments.find_one({"deployment_id": deployment_id})

    async def get_user_deployment(self, user_id: int):
        user = await self.get_user(user_id)
        if user and user.get("active_management_id"):
            dep = await self.get_deployment(user["active_management_id"])
            if dep:
                return dep
        cursor = self.db.deployments.find(
            {"user_id": user_id, "status": {"$in": ["running", "deploying", "starting"]}}
        ).sort("created_at", -1).limit(1)
        deps = await cursor.to_list(length=1)
        return deps[0] if deps else None

    async def get_all_user_deployments(self, user_id: int):
        return await self.db.deployments.find({"user_id": user_id}).to_list(None)

    async def update_deployment(self, deployment_id: str, data: dict):
        await self.db.deployments.update_one({"deployment_id": deployment_id}, {"$set": data})

    async def delete_deployment(self, deployment_id: str):
        await self.db.deployments.delete_one({"deployment_id": deployment_id})

    async def count_active_deployments(self):
        return await self.db.deployments.count_documents({"status": "running"})

    async def count_total_deployments(self):
        return await self.db.deployments.count_documents({})

    # ---- Railway Token Operations ----
    async def add_railway_token(self, token: str, added_by: int):
        doc = {
            "token": token,
            "added_by": added_by,
            "added_at": __import__("datetime").datetime.utcnow(),
            "is_active": True,
            "is_available": True,
            "current_deployments": 0,
            "max_deployments": 2,
            "credits": 5.0,
            "total_deployments": 0,
            "priority": 0,
        }
        await self.db.railway_tokens.update_one(
            {"token": token},
            {"$set": doc},
            upsert=True
        )
        return doc

    async def get_railway_token(self, token: str):
        return await self.db.railway_tokens.find_one({"token": token})

    async def get_available_token(self):
        return await self.db.railway_tokens.find_one_and_update(
            {
                "is_active": True, "is_available": True, "is_restricted": {"$ne": True},
                "$expr": {"$lt": ["$current_deployments", "$max_deployments"]},
            },
            {"$inc": {"current_deployments": 1}},
            sort=[("priority", -1), ("credits", -1)],
        )

    async def release_token(self, token: str):
        await self.db.railway_tokens.update_one({"token": token}, {"$inc": {"current_deployments": -1}})

    async def disable_token(self, token: str):
        await self.db.railway_tokens.update_one({"token": token}, {"$set": {"is_active": False, "is_available": False, "current_deployments": 0}})

    async def update_token_deployments(self, token: str):
        await self.db.railway_tokens.update_one({"token": token}, {"$inc": {"current_deployments": 1, "total_deployments": 1}})

    async def update_token_priority(self, token: str, priority: int):
        await self.db.railway_tokens.update_one({"token": token}, {"$set": {"priority": priority}})

    async def get_all_tokens(self):
        return await self.db.railway_tokens.find({}).to_list(None)

    async def count_active_tokens(self):
        return await self.db.railway_tokens.count_documents({"is_active": True})

    async def delete_token(self, token: str):
        await self.db.railway_tokens.delete_one({"token": token})

    async def restrict_token(self, token: str):
        await self.db.railway_tokens.update_one({"token": token}, {"$set": {"is_restricted": True}})

    async def unrestrict_token(self, token: str):
        await self.db.railway_tokens.update_one({"token": token}, {"$unset": {"is_restricted": ""}})

    async def get_restricted_tokens(self) -> list:
        return await self.db.railway_tokens.find({"is_restricted": True}).to_list(None)

    # ---- Force Subscribe ----
    async def add_channel(self, channel_id: int, invite_link: str, name: str = ""):
        await self.db.force_subs.update_one(
            {"channel_id": channel_id},
            {"$set": {"channel_id": channel_id, "invite_link": invite_link, "name": name}},
            upsert=True,
        )

    async def remove_channel(self, channel_id: int):
        await self.db.force_subs.delete_one({"channel_id": channel_id})

    async def get_all_channels(self):
        return await self.db.force_subs.find({}).to_list(None)

    # ---- Plans ----
    async def create_plan(self, data: dict):
        await self.db.plans.insert_one(data)
        return data

    async def get_plan(self, plan_id: str):
        return await self.db.plans.find_one({"plan_id": plan_id})

    async def get_all_plans(self):
        return await self.db.plans.find({}).to_list(None)

    async def update_plan(self, plan_id: str, data: dict):
        await self.db.plans.update_one({"plan_id": plan_id}, {"$set": data})

    async def delete_plan(self, plan_id: str):
        await self.db.plans.delete_one({"plan_id": plan_id})

    # ---- Wallet ----
    async def get_wallet(self, user_id: int):
        return await self.db.wallet.find_one({"user_id": user_id})

    async def create_wallet(self, user_id: int):
        wallet = {"user_id": user_id, "balance": 0, "total_deposited": 0, "total_spent": 0, "transactions": []}
        await self.db.wallet.insert_one(wallet)
        return wallet

    async def add_transaction(self, user_id: int, tx: dict):
        await self.db.wallet.update_one({"user_id": user_id}, {"$push": {"transactions": tx}})

    # ---- Referrals ----
    async def create_referral(self, user_id: int, code: str):
        await self.db.referrals.insert_one({"user_id": user_id, "code": code, "referrals": [], "total_points": 0})

    async def get_referral_by_code(self, code: str):
        return await self.db.referrals.find_one({"code": code})

    async def add_referral(self, user_id: int, referred_id: int):
        await self.db.referrals.update_one({"user_id": user_id}, {"$push": {"referrals": referred_id}, "$inc": {"total_points": settings.REFERRAL_BONUS}})

    # ---- Logs ----
    async def add_log(self, log_type: str, data: dict):
        log = {"type": log_type, "data": data, "timestamp": __import__("datetime").datetime.utcnow()}
        await self.db.logs.insert_one(log)

    async def get_recent_logs(self, limit: int = 50):
        return await self.db.logs.find({}).sort("timestamp", -1).limit(limit).to_list(None)

    # ---- Analytics ----
    async def get_db_stats(self):
        return await self.db.command("dbStats")

    async def reset_current_deployments(self):
        try:
            tokens = await self.db.railway_tokens.find({}).to_list(None)
            for t in tokens:
                token = t["token"]
                active_count = await self.db.deployments.count_documents({
                    "railway_token": token,
                    "status": {"$in": ["running", "deploying", "starting"]}
                })
                await self.db.railway_tokens.update_one(
                    {"token": token},
                    {"$set": {"current_deployments": active_count}}
                )
        except Exception as e:
            pass


database = Database()
