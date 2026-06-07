<script>
    // 1. Hàm hiển thị thông báo toast
    function showNotification(message, type='success'){
        const container = document.getElementById('toast-container');
        if (!container) return; 
        
        const toast = document.createElement('div');
        toast.className = `custom-toast ${type}`;

        const iconClass = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle';
        
        toast.innerHTML = `
            <i class="fa ${iconClass} toast-icon"></i>
            <span class="toast-message">${message}</span>
        `;

        container.appendChild(toast);
        toast.offsetHeight;
        toast.classList.add('show');

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => { toast.remove(); }, 350);
        }, 3500);
    }

    document.addEventListener("DOMContentLoaded", function() {
        // ĐĂNG KÝ CHẶN MẠNG NGẦM ĐỂ CHẠY LOCAL OFFLINE
        if (window.Formio) {
            Formio.setBaseUrl(window.location.origin + '/mock-formio');
            Formio.setProjectUrl(window.location.origin + '/mock-formio/project/local');
            Formio.loadProject = () => Promise.resolve({_id: "local", name: "local", setting: {} });
            if (Formio.prototype) {
                Formio.prototype.loadProject = () => Promise.resolve({ _id: "local", name: "local", setting: {} });
            }
        }

        // ĐÃ SỬA CÚ PHÁP COMMENT: Đồng bộ chuẩn tên biến formSchema và schema_json_str từ Django View
        let formSchema = {{ schema_json_str | safe }};
        if (!formSchema || !formSchema.components) {
            formSchema = { components: [] };
        }

        // ĐÃ SỬA ID: Khởi dựng Form.io trỏ đúng vào vùng chứa 'formio-render-area'
        Formio.createForm(document.getElementById('formio-render-area'), formSchema, {
            noDefaultSubmitButton: false,
            buttonSettings: { showCancel: false }
        })
        .then(function(formInstance) {
            // Ẩn màn hình loading khi form đã dựng thành công
            const loader = document.getElementById('loading-screen');
            if(loader) { loader.classList.add('hidden'); }

            // Chặn hành vi gửi dữ liệu mặc định lên Cloud của Form.io
            formInstance.nosubmit = true;

            // Lắng nghe sự kiện click nút Submit trên Form.io
            formInstance.on('submit', function(submission) {
                
                // ĐÃ SỬA CÚ PHÁP COMMENT: Ghi chính xác URL của API nhận submission trong Django
                fetch("{% url 'submit_form_api' form_def.id %}", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": "{{ csrf_token }}"
                    },
                    body: JSON.stringify(submission.data) 
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error("Phản hồi từ máy chủ Django thất bại.");
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.status === 'success') {
                        showNotification("Bạn đã nộp biểu mẫu thành công!", "success");
                        formInstance.emit('submitDone', submission); 
                        
                        // Chuyển hướng người dùng về trang danh sách sau 2 giây
                        setTimeout(() => {
                            window.location.href = "{% url 'list_forms' %}";
                        }, 2000);
                    } else {
                        showNotification("Có lỗi xảy ra: " + data.message, "error");
                        formInstance.emit('submitError');
                    }
                })
                .catch(err => {
                    console.error("Lỗi kết nối API:", err);
                    showNotification("Không thể kết nối đến máy chủ để lưu kết quả.", "error");
                    formInstance.emit('submitError');
                });
            });
        })
        .catch(function(err) {
            console.error("Lỗi khởi tạo Form.io Render:", err);
            showNotification("Không thể hiển thị cấu trúc biểu mẫu này.", "error");
        });
    });
</script>