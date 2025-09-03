from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ConversationStateModel(BaseModel):
    policy_number: str
    question: str
    document_text: str
    insurance_provider: Optional[str] = None
    policyholder_name: Optional[str] = None
    policy_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    history: List = []
    fraud: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for LangGraph"""
        return self.dict()
