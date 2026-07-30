from app.core.config import APP_LANG

_MESSAGES = {
    "en": {
        "SignatureDoesNotMatch": "The request signature we calculated does not match",
        "NoSuchBucket": "The specified bucket does not exist",
        "NoSuchKey": "The specified key does not exist",
        "InvalidRequest": "Invalid request",
        "EntityTooLarge": "Object exceeds maximum allowed size",
        "SlowDown": "Reduce request rate",
        "ServiceUnavailable": "Storage backend is temporarily unavailable",
        "NoSuchUpload": "The specified multipart upload does not exist",
        "MissingContentLength": "Content-Length header is required",
        "InvalidPart": "One or more of the specified parts could not be found",
        "EntityTooSmall": "Your proposed upload is smaller than the minimum allowed size",
        "PreconditionFailed": "At least one of the preconditions you specified did not hold",
        "AccessDenied": "Access Denied",
        "NotImplemented": "Not implemented",
    },
    "zh": {
        "SignatureDoesNotMatch": "请求签名校验失败",
        "NoSuchBucket": "存储桶不存在",
        "NoSuchKey": "对象不存在",
        "InvalidRequest": "无效请求",
        "EntityTooLarge": "对象超过允许的最大大小",
        "SlowDown": "请降低请求频率",
        "ServiceUnavailable": "存储后端暂时不可用",
        "NoSuchUpload": "分段上传不存在",
        "MissingContentLength": "缺少 Content-Length 头",
        "InvalidPart": "一个或多个分段不存在",
        "EntityTooSmall": "分段小于允许的最小大小",
        "PreconditionFailed": "前置条件失败",
        "AccessDenied": "拒绝访问",
        "NotImplemented": "未实现",
    },
}


def s3_message(code: str, fallback: str | None = None) -> str:
    lang = APP_LANG if APP_LANG in _MESSAGES else "en"
    return _MESSAGES[lang].get(code, fallback or code)
