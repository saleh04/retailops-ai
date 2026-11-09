from enum import Enum


class MessageRole(str, Enum):
    USER = "user"            
    ASSISTANT = "assistant"  
    TOOL = "tool"           
    
class MessageStatus(str, Enum):
    SUCCESS = "success"      
    NO_DATA = "no_data"  
    FAILED = "failed"       