// A stand-in for ZRA's VSDC, for end-to-end tests. Answers like the VSDC API spec's samples.
// Run: node fake-vsdc.mjs  (port 8091), then set the VSDC address in Settings to
//   http://localhost:8091/zrasandboxvsdc
import { createServer } from "node:http";

let receipt = 0;

function send(res, body) {
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ resultMsg: "It is succeeded", resultDt: "20261101120000", ...body }));
}

createServer((req, res) => {
  let raw = "";
  req.on("data", (chunk) => (raw += chunk));
  req.on("end", () => {
    const body = raw ? JSON.parse(raw) : {};
    const path = req.url.replace(/^\/[^/]+/, "");
    if (path === "/initializer/selectInitInfo") {
      if (body.dvcSrlNo === "bad")
        return send(res, { resultCd: "901", resultMsg: "It is not valid device" });
      return send(res, {
        resultCd: "000",
        data: { info: { sdcId: "SDC0010000553", mrcNo: "WIS00001092" } },
      });
    }
    if (path === "/items/saveItem" || path === "/items/updateItem") {
      return send(res, { resultCd: "000", data: null });
    }
    if (path === "/trnsSales/saveSales") {
      receipt += 1;
      const sign = `FAKESIGN${String(receipt).padStart(8, "0")}`;
      return send(res, {
        resultCd: "000",
        data: {
          rcptNo: receipt,
          intrlData: `FAKEINTERNALDATA${receipt}`,
          rcptSign: sign,
          vsdcRcptPbctDate: "20261101120000",
          sdcId: "SDC0010000553",
          mrcNo: "WIS00001092",
          qrCodeUrl: `https://sandboxportal.zra.org.zm/common/link/ebm/receipt/indexEbmReceiptData?Data=${body.tpin}000${sign}`,
        },
      });
    }
    send(res, { resultCd: "999", resultMsg: `Unknown path ${path}` });
  });
}).listen(8091, () => console.log("fake VSDC on :8091"));
