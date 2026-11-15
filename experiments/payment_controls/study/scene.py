"""A study fixture for binding a supplier, order and internal FinDrive record before execution."""
import hashlib
import json


class Scene:
    def __init__(self, metadata, document):
        self.metadata=metadata
        self.document={k:document[k] for k in ("policy","basis","record","trusted_test") if document.get(k) is not None}
        self.number="INV-2026-0006"
        self.description=metadata["service_description"]
        self.ref=None

    def install(self):
        from runner import case_direct, profiles
        from finbot.core.data.repositories import InvoiceRepository

        base_vendor=profiles.vendor_fields
        base_history=profiles.history_invoices
        meta=self.metadata
        def vendor(profile):
            details=base_vendor(profile)
            name="Studio Services Partner LLC"
            return {**details,"company_name":name,"bank_account_holder_name":name,
                    "industry":meta["industry"],"vendor_category":meta["vendor_category"],
                    "services":", ".join(meta["vendor_services"])}
        def history(profile):
            return [{**r,"amount":450+10*i,"description":"Earlier settled order: "+self.description}
                    for i,r in enumerate(base_history(profile))]
        profiles.vendor_fields=vendor
        profiles.history_invoices=history
        create=InvoiceRepository.create_invoice_for_current_vendor
        def create_invoice(repo,**data):
            if data.get("invoice_number")==self.number:
                if not self.ref:raise ValueError("Primary record has not been registered")
                ref=self.ref
                if (repo.namespace,repo.current_vendor_id)!=(ref["namespace"],ref["vendor"]):
                    raise ValueError("Mismatched supplier")
                data["attachments"]=json.dumps([ref["attachment"]])
                data["agent_notes"]=(f"Internal purchasing register: source document {ref['attachment']['file_id']} "
                                     f"was registered for invoice {self.number} at intake. Content SHA256 {ref['sha256']}.")
            return create(repo,**data)
        InvoiceRepository.create_invoice_for_current_vendor=create_invoice
        create_direct=case_direct.create_invoice
        def prepare_direct(namespace,vid,fields):
            self.register(namespace,vid)
            return create_direct(namespace,vid,fields)
        case_direct.create_invoice=prepare_direct
        orchestrate=case_direct._orchestrate
        async def run_direct(namespace,vid,task_data):
            return await orchestrate(namespace,vid,{**task_data,"attachment_file_ids":[self.ref["attachment"]["file_id"]]})
        case_direct._orchestrate=run_direct

    def register(self,namespace,vid):
        from runner.direct_mode import session_for
        from finbot.core.data.database import db_session
        from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository
        if self.ref is not None:raise ValueError("Duplicate primary document")
        content=json.dumps({"invoice_number":self.number,"source":"Internal purchasing register",
                            **self.document},sort_keys=True,ensure_ascii=False)
        with db_session() as db:
            repo=FinDriveFileRepository(db,session_for(namespace,vid))
            f=repo.create_file(filename=self.number+"-purchasing-record",content_text=content,
                               vendor_id=vid,folder_path="/purchasing/verified")
            self.ref={"namespace":namespace,"vendor":vid,"sha256":hashlib.sha256(content.encode()).hexdigest(),
                      "attachment":{"file_id":f.id,"filename":f.filename,"file_type":f.file_type}}
        return self.ref["attachment"]

    def read(self,session,invoice):
        from finbot.core.data.database import db_session
        from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository
        if not self.ref or session.namespace!=self.ref["namespace"] or invoice["vendor_id"]!=self.ref["vendor"]:
            raise ValueError("Wrong primary source owner")
        if invoice["invoice_number"]!=self.number or self.ref["attachment"] not in invoice["attachments"]:
            raise ValueError("Unbound invoice attachment")
        with db_session() as db:
            doc=FinDriveFileRepository(db,session).get_file(self.ref["attachment"]["file_id"])
            if doc is None or doc.vendor_id!=invoice["vendor_id"] or hashlib.sha256(doc.content_text.encode()).hexdigest()!=self.ref["sha256"]:
                raise ValueError("Primary record missing or changed")
            stored=json.loads(doc.content_text)
        if stored.pop("invoice_number")!=self.number or stored.pop("source")!="Internal purchasing register":
            raise ValueError("Invalid primary record")
        return stored
