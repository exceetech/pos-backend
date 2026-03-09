from pydantic import BaseModel


class BillingSettingsResponse(BaseModel):
    default_gst: float
    printer_layout: str


class BillingSettingsUpdate(BaseModel):
    default_gst: float
    printer_layout: str