with open("app/routes/admin_catalog_routes.py", "r") as f:
    content = f.read()

# 1. Update UnverifiedVariantOut
content = content.replace("    unit: str\n", "    unit: str\n    brand: Optional[str] = None\n")

# 2. Update UnverifiedVariantOut creation in GET
content = content.replace("            label=(v.variant_name or \"(no variant)\"),\n            unit=v.unit,\n", 
                          "            label=(v.variant_name or \"(no variant)\"),\n            unit=v.unit,\n            brand=v.brand,\n")

# 3. Update EditVariantRequest
content = content.replace("    variant_name: Optional[str] = None\n", "    variant_name: Optional[str] = None\n    brand: Optional[str] = None\n    unit: Optional[str] = None\n")

# 4. Update PATCH logic
patch_logic = """    if data.hsn_code is not None:
        variant.hsn_code = data.hsn_code.strip() or None"""
new_patch_logic = """    if data.brand is not None:
        variant.brand = data.brand.strip() or None
    if data.unit is not None:
        variant.unit = data.unit.strip() or None
    if data.hsn_code is not None:
        variant.hsn_code = data.hsn_code.strip() or None"""
content = content.replace(patch_logic, new_patch_logic)

with open("app/routes/admin_catalog_routes.py", "w") as f:
    f.write(content)
