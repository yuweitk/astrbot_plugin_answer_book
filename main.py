from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio
import json
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.conversation_mgr import Conversation

# 用户使用记录存储
user_records: Dict[str, datetime] = {}

@register("answer_book", "雨爲/yuweitk", "基于LLM的答案之书插件", "1.0.0", "https://github.com/yuweitk/astrbot_plugin_answer_book")
class AnswerBookPlugin(Star):
    def __init__(self, context: Context, config: Dict):
        super().__init__(context)
        self.config = config
        self.cooldown = timedelta(minutes=self.config.get("cooldown_minutes", 10))
        self.banned_keywords = self.config.get("banned_keywords", "政治\n色情\n反动\n恐怖\n暴力\n毒品\n赌博").split("\n")
        
    @filter.command("答案之书")
    async def answer_book(self, event: AstrMessageEvent, question: Optional[str] = None):
        '''答案之书 - 获取问题的理性分析和建议
        
        使用方法：
        /答案之书 [你的问题]
        示例：
        /答案之书 我该选择哪份工作？
        /答案之书 如何提高工作效率？
        '''
      
        # 如果没有提供问题参数，显示使用帮助
        if not question:
            help_text = (
                "📖 答案之书使用说明：\n"
                "请发送：/答案之书 [你的问题]\n\n"
                "示例：\n"
                "• /答案之书 我该选择哪份工作？\n"
                "• /答案之书 如何提高工作效率？\n"
                "• /答案之书 学习新技能有什么建议？\n\n"
                "注意：每个问题之间有{cooldown}分钟冷却时间"
            ).format(cooldown=self.cooldown.seconds // 60)
            yield event.plain_result(help_text)
            return
        
        # 检查用户是否在冷却期内
        user_id = event.get_sender_id()
        last_used = user_records.get(user_id)
        
        if last_used and datetime.now() - last_used < self.cooldown:
            remaining = (last_used + self.cooldown - datetime.now()).seconds // 60
            yield event.plain_result(f"⏳ 请等待{remaining}分钟后再提问，让答案之书有时间思考。")
            return
        
        # 检查问题是否包含违禁内容
        if any(keyword.strip() and keyword in question for keyword in self.banned_keywords):
            yield event.plain_result("🚫 问题包含不当内容，答案之书无法回答。")
            return
        
        # 记录用户使用时间
        user_records[user_id] = datetime.now()
        
        # 获取当前对话上下文（包括知识库内容）
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        contexts = []
        
        if curr_cid:
            conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, curr_cid)
            if conversation and conversation.history:
                try:
                    contexts = json.loads(conversation.history)
                except json.JSONDecodeError:
                    contexts = []
        
        # 调用LLM获取答案
        try:
            # 设置系统提示词
            system_prompt = (
                "你是一本答案之书，用户会向你提出各种问题。"
                "请根据你的知识和理解，给出理性、客观的回答。"
                "回答应该清晰、有逻辑性，可以包含分析和建议。"
                "如果问题涉及专业知识，请参考相关知识库内容。"
            )
            
            # 调用LLM（通过AstrBot的标准接口，确保知识库集成）
            yield event.request_llm(
                prompt=question,
                func_tool_manager=self.context.get_llm_tool_manager(),
                session_id=curr_cid,
                contexts=contexts,
                system_prompt=system_prompt,
                conversation=curr_cid and await self.context.conversation_manager.get_conversation(event.unified_msg_origin, curr_cid)
            )
                
        except Exception as e:
            logger.error(f"答案之书插件错误: {str(e)}")
            yield event.plain_result("⚠️ 答案之书暂时无法回答这个问题，请稍后再试。")
    
    async def terminate(self):
        '''插件卸载时清理'''
        user_records.clear()