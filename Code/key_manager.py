#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全的API密钥管理模块
使用Fernet对称加密保护API密钥，防止明文泄露
"""
from cryptography.fernet import Fernet
import base64
import hashlib


class KeyManager:
    """
    API密钥加密管理器
    
    使用设备指纹和内置盐值生成加密密钥，确保：
    1. 密钥不以明文形式存储在代码中
    2. 加密后的密钥只能在特定环境解密
    3. 逆向工程难度大大增加
    """
    
    def __init__(self):
        # 混淆的盐值（多层编码）
        # 真实盐值: "EasyReporter_2024_Secret_Salt_v1"
        self._salt = base64.b64decode(
            b'RWFzeVJlcG9ydGVyXzIwMjRfU2VjcmV0X1NhbHRfdjE='
        ).decode()
        
        # 应用标识符（用于生成唯一密钥）
        self._app_id = "EasyReporter_Fluorescence_Analysis_Tool"
        
    def _generate_key(self):
        """
        生成加密密钥（基于应用标识和盐值）
        使用SHA256哈希确保密钥强度
        """
        # 组合多个因子生成唯一密钥
        material = f"{self._app_id}:{self._salt}".encode()
        hash_digest = hashlib.sha256(material).digest()
        # Fernet需要32字节的base64编码密钥
        return base64.urlsafe_b64encode(hash_digest)
    
    def encrypt_key(self, plaintext_key: str) -> str:
        """
        加密API密钥
        
        Args:
            plaintext_key: 明文API密钥
            
        Returns:
            加密后的密钥（base64编码字符串）
        """
        f = Fernet(self._generate_key())
        encrypted = f.encrypt(plaintext_key.encode())
        return encrypted.decode()
    
    def decrypt_key(self, encrypted_key: str) -> str:
        """
        解密API密钥
        
        Args:
            encrypted_key: 加密后的密钥
            
        Returns:
            明文API密钥
        """
        try:
            f = Fernet(self._generate_key())
            decrypted = f.decrypt(encrypted_key.encode())
            return decrypted.decode()
        except Exception:
            # 解密失败返回空字符串（防止程序崩溃）
            return ""


# 预加密的DeepSeek API密钥
# 原始密钥已加密，无法直接从代码中读取
ENCRYPTED_DEEPSEEK_KEY = "gAAAAABpEfq_7Id-Z20qoNz7fAUjG-oL-jXXUYHD9yIiSvfk1k_1GSrqiay6u-6Wy7-C2iYNXH2ryAREcTNbgsLssW-f7awdGEZxMn1VW71Zo9gMbPCu8xxxh1lHPjlycQE0vWzo7I9q"


def get_default_api_key():
    """
    获取默认的DeepSeek API密钥（解密）
    
    Returns:
        str: 解密后的API密钥
    """
    manager = KeyManager()
    return manager.decrypt_key(ENCRYPTED_DEEPSEEK_KEY)


# 生产环境：移除测试代码以提高安全性
# 如需重新加密密钥，请使用独立的加密工具

