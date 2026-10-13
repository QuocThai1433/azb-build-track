# AZB Project Hub — Ứng dụng quản lý dự án thi công

Ứng dụng Python chạy trên máy tính cá nhân qua `localhost`, thiết kế theo hướng dashboard quản lý dự án thi công. Bộ mã nguồn được khởi tạo từ file `data/Ke_hoach_thi_cong_Nha_may_Ton_Dong_A.xlsx` mà bạn cung cấp.

## 1. Các chức năng có sẵn (bản nâng cấp UI + quản lý công việc 1.1)

- **Tổng quan:** tiến độ kế hoạch, công việc đã cập nhật thực tế, rủi ro còn mở, ngân sách và mốc thời gian.
- **Thông tin dự án:** chủ đầu tư, nhà thầu, gói thầu, mốc thời gian, giá trị hợp đồng tham chiếu.
- **Công việc & tiến độ:** WBS; tìm kiếm/lọc; thêm, sửa, xóa; cập nhật % tiến độ thực tế, trạng thái, người phụ trách và ngày thực tế. Bản 1.1 bổ sung mức ưu tiên (Khẩn cấp/Cao/Trung bình/Thấp), bộ lọc ưu tiên, bộ lọc công việc quá hạn, cảnh báo quá hạn và sắp xếp ưu tiên trước. Khi nhập lại Excel, mức ưu tiên được giữ lại cho công việc có mã WBS trùng.
- **Biểu đồ Gantt:** hiển thị lịch dự kiến của các đầu việc theo ngày bắt đầu/kết thúc trong Excel.
- **Nguồn lực:** nhân sự ban chỉ huy, công nhật, thiết bị và vận chuyển; có thể thêm/sửa/xóa.
- **Chi phí & ngân sách:** 63 dòng chi phí Prelim được nạp sẵn; phân biệt dự toán và thực chi; có thể thêm/sửa/xóa khoản chi.
- **Rủi ro & kiến nghị:** 17 mục rủi ro từ file gốc; theo dõi mức độ, người phụ trách, hạn xử lý và trạng thái.
- **An toàn HSSE:** chỉ tiêu HSSE nguồn và sổ ghi nhận kiểm tra an toàn/sự cố/near miss/hành động khắc phục.
- **Nhật ký công trường:** ngày, thời tiết, quân số, công việc thực hiện, vướng mắc.
- **Biện pháp thi công:** hạng mục công trình tạm, điện nước tạm và chỉ số khối lượng từ file nguồn.
- **Nhập Excel:** nạp lại workbook có cấu trúc sheet tương tự file gốc.
- **Xuất báo cáo:** xuất workbook tổng hợp gồm các sheet Tổng quan, Tiến độ, Nguồn lực, Chi phí, Rủi ro, Biện pháp, HSSE và Nhật ký.

## 2. Chạy nhanh trên Windows

### Cách dễ nhất

1. Giải nén file `AZB_Project_Hub_Premium_UI.zip` vào thư mục muốn lưu, ví dụ `C:\Users\<tên_user>\Desktop\AZB_Project_Hub`.
2. Cài Python 3.11 trở lên từ trang chính thức `https://www.python.org/downloads/` (khuyến nghị Python 3.12). Nếu cài mới, chọn **Add Python to PATH**.
3. Mở thư mục đã giải nén. Nhấp đúp file `start.bat`.
4. Script tự tạo môi trường `.venv`, cài thư viện trong `requirements.txt` và chạy ứng dụng. Lần đầu cần kết nối Internet/proxy để tải Flask và openpyxl.
5. Mở Chrome/Edge tại **http://127.0.0.1:5000**.
6. Giữ cửa sổ terminal đang chạy. Khi muốn tắt ứng dụng, quay lại cửa sổ đó và nhấn `Ctrl + C`.

## 3. Chạy bằng VS Code

1. Mở VS Code → **File → Open Folder...** → chọn thư mục `AZB_Project_Hub` đã giải nén.
2. Chọn **Terminal → New Terminal**.
3. Chạy lần lượt các lệnh sau trong PowerShell (ví dụ nếu máy đã có Python 3.12):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Nếu PowerShell chặn kích hoạt môi trường ảo, chạy trực tiếp:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Nếu máy không có Python 3.12 nhưng đã có Python khác, dùng `py -m venv .venv` thay cho dòng đầu. VS Code có sẵn cấu hình `.vscode/launch.json`; chọn **Run and Debug → AZB Project Hub (Flask)** để chạy bằng debugger.

Sau khi terminal cho biết Flask đang chạy, truy cập **http://127.0.0.1:5000**.

## 4. Dữ liệu được lưu ở đâu?

- `data/seed_data.json`: dữ liệu khởi tạo trích từ workbook nguồn.
- `data/Ke_hoach_thi_cong_Nha_may_Ton_Dong_A.xlsx`: file Excel gốc được đóng gói kèm.
- `instance/project_manager.db`: SQLite tự tạo ở lần khởi chạy đầu tiên. Các thay đổi được lưu tại đây, không mất khi tắt ứng dụng.
- `instance/uploads/`: các file Excel tải lên khi nhập dữ liệu mới.

Để sao lưu, vào **Báo cáo & xuất file → Tải báo cáo Excel**. Muốn sao lưu toàn bộ trạng thái để phục hồi y nguyên, hãy dừng ứng dụng và sao chép `instance/project_manager.db`.

## 5. Quy trình sử dụng đề xuất

1. Vào **Thông tin dự án** để rà soát ngày báo cáo và giá trị hợp đồng. File gốc có ghi chú cần xác nhận cơ sở hợp đồng 192 tỷ hay 280 tỷ.
2. Vào **Công việc & tiến độ** để cập nhật % thực tế, trạng thái, người phụ trách và ngày thực tế.
3. Vào **Chi phí & ngân sách** để ghi thực chi sau khi đối chiếu chứng từ.
4. Phân công người phụ trách/hạn xử lý tại **Rủi ro & kiến nghị**.
5. Ghi **Nhật ký công trường** và **An toàn HSSE** theo ngày.
6. Xuất báo cáo Excel để lưu hồ sơ hoặc chia sẻ với các bên liên quan.

## 6. Lưu ý quan trọng

- App mặc định chỉ lắng nghe tại `127.0.0.1`, tức máy tính hiện tại. Không tự ý đổi thành `0.0.0.0` hoặc mở cổng ra Internet.
- Đây là bản local, chưa có đăng nhập/phân quyền nhiều người dùng; phù hợp để chạy/thử nghiệm trên một máy.
- Tiến độ thực tế và thực chi **được để chưa cập nhật**; ứng dụng không tự sao chép phần trăm kế hoạch thành phần trăm thực tế.
- Các cảnh báo trong workbook gốc là phân tích sơ bộ, cần ban chỉ huy/phòng kế hoạch/QS xác nhận trước khi dùng làm kết luận chính thức.
- Khi nhập Excel mới, dữ liệu kế hoạch chính đồng bộ theo file; tiến độ thực tế giữ lại theo mã WBS trùng, thực chi giữ theo tên khoản chi trùng, còn nhật ký công trường/HSSE đã ghi không bị xóa.

## Công nghệ

Python · FastAPI (chạy bằng Uvicorn) · SQLAlchemy 2.0 · Alembic · SQLite · OpenPyXL · Jinja2 · HTML/CSS/JavaScript. Giao diện tự xây, không cần cài framework front-end riêng. Phần giao diện nâng cấp nằm ở `static/css/premium.css`; có thể chỉnh màu sắc, khoảng cách, trạng thái hover và bố cục responsive tại đây mà không đụng đến logic Python.

## Cấu trúc mã nguồn (v2.0: FastAPI + SQLAlchemy)

```
app.py                  điểm chạy: python app.py  → http://127.0.0.1:5000
azb_hub/
  main.py               tạo ứng dụng, gắn middleware, static, các router
  db.py                 kết nối SQLite, Session, chạy migration khi khởi động
  models.py             8 bảng dưới dạng model SQLAlchemy
  schemas.py            model Pydantic đọc dữ liệu form (nhận cả số kiểu 1,5)
  repositories.py       TOÀN BỘ truy vấn cơ sở dữ liệu
  services/             logic nghiệp vụ: thống kê, Gantt, nhập/xuất Excel, dữ liệu mẫu
  routers/              các trang web; chỉ nhận request rồi gọi repositories/services
  web.py                Jinja2, bộ lọc tiền tệ, thông báo flash, redirect 303
migrations/             lịch sử thay đổi cấu trúc cơ sở dữ liệu (Alembic)
tests/                  bộ kiểm thử tự động (pytest)
```

- **Thêm cột / bảng:** sửa `azb_hub/models.py`, rồi chạy `alembic revision --autogenerate -m "mô tả"`. Lần khởi động sau ứng dụng tự áp dụng migration. Cơ sở dữ liệu cũ (từ bản Flask) được nhận nguyên vẹn, không mất dữ liệu.
- **Nhiều dự án (v2.1):** mỗi trang của một dự án nằm dưới `/<tên-dự-án>/...` (ví dụ `/nha-may-xi-mang/tasks`; phần tên được tự tạo từ tên dự án, link cũ `/p/<số>/...` vẫn chuyển hướng đúng). Chọn dự án ở ô "Không gian làm việc" trên thanh bên trái. Trang `/projects` liệt kê mọi dự án, cho lưu trữ, khôi phục hoặc xoá. Xoá dự án không cần lưu trữ trước; hộp xác nhận chỉ hỏi có chắc chắn xoá hay không. Không xoá được dự án cuối cùng, và database được tự sao lưu (`..._truoc_xoa_du_an_<ngày_giờ>.db`) ngay trước khi xoá. Mọi bảng dữ liệu có cột `project_id`; mọi truy vấn trong `repositories.py` đều lọc theo dự án.
- **Nhập Excel:** mặc định file tải lên thành **một dự án mới**, các dự án đang có không đổi. Chọn "Cập nhật dự án này" khi file là phiên bản mới của chính dự án đang mở (giữ tiến độ thực tế theo mã WBS).
- **Nhập Excel linh hoạt (v2.2):** sau khi chọn file có bước **xem trước**. App nhận diện sheet và cột theo **tên tiêu đề** (không cần đúng vị trí của mẫu AZB), cho bạn sửa cách ghép cột trước khi nhập, và ghi nhớ lựa chọn cho các file sau (bảng `import_aliases`). Ô trống hoặc cột không có thì để trống, vẫn nhập được. Khi **cập nhật dự án**: sheet không có trong file thì giữ nguyên dữ liệu cũ; cột không có thì giữ giá trị cũ của dòng khớp; công việc khớp theo mã WBS, không có mã thì khớp theo tên. Từ đồng nghĩa của tên cột nằm ở `azb_hub/services/excel_mapping.py` (`ENTITIES`).
- **Nâng cấp database:** lần đầu chạy bản này, app tự sao lưu database (`instance/backups/project_manager_truoc_nang_cap_<ngày_giờ>.db`) rồi chuyển dữ liệu cũ thành dự án số 1.
- **Sao lưu khi nhập Excel:** trang Nhập Excel cho chọn "Sao lưu rồi mới nhập" (mặc định) hoặc "Nhập luôn, không sao lưu". Bản sao nằm ở `instance/backups/project_manager_<ngày_giờ>.db`. Khôi phục: tắt ứng dụng rồi chép file đó về `instance/project_manager.db`.
- **Chạy kiểm thử:** `pip install -r requirements-dev.txt` rồi `python -m pytest tests`.
- **Quy tắc:** route không viết SQL; mọi truy vấn nằm trong `repositories.py`.
- Bản Flask trước khi chuyển đổi được lưu ở thư mục `_flask_backup/` (có thể xóa khi đã yên tâm).

## Giao diện Enterprise (v1.2)
- Thêm lớp giao diện `static/css/enterprise.css` theo phong cách phần mềm doanh nghiệp: nền trung tính, sidebar navy, điểm nhấn xanh, thẻ KPI, bảng/form và trạng thái nhất quán.
- Thanh điều hướng nhanh ở header: gõ tên chức năng, chọn kết quả hoặc nhấn Enter; phím tắt `Ctrl+K` / `Cmd+K` để mở tìm kiếm.
- Bố cục responsive cho màn hình máy tính bảng và điện thoại; giữ nguyên các route, template và dữ liệu ứng dụng hiện có.


## Enterprise UI Ultra (v1.3)
- Nâng cấp toàn bộ lớp giao diện bằng `static/css/ultra.css`: hệ màu navy/indigo/teal, sidebar có trạng thái active rõ, header tìm kiếm nhanh, thẻ KPI, panel biểu đồ, bảng dữ liệu, bộ lọc và form nhất quán.
- Tối ưu responsive cho desktop/tablet/mobile; thêm nền che khi mở menu trên màn hình nhỏ, đóng bằng Escape hoặc bấm ra ngoài.
- Thêm trạng thái focus dễ nhìn, chuyển động nhẹ và tôn trọng thiết lập giảm chuyển động của hệ điều hành. Không thay đổi schema dữ liệu hoặc route xử lý nghiệp vụ.
