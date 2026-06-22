UPLOAD_TYPE_LOGISTICS = "物流"
UPLOAD_TYPE_WAREHOUSE = "仓库"
VALID_UPLOAD_TYPES = {UPLOAD_TYPE_LOGISTICS, UPLOAD_TYPE_WAREHOUSE}
DEFAULT_UPLOAD_TYPE = UPLOAD_TYPE_LOGISTICS

# doc_type 到用友云 businessType 的映射
# 上传到用友云(物流类)时按单据类型选择对应的业务类型
DOC_TYPE_TO_BUSINESS_TYPE = {
    "销售": "yonbip-scm-scmsa",
    "转库": "yonbip-scm-stock",
    "其他": "yonbip-scm-stock",
}
