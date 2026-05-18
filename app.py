import random
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, session, redirect
from supabase import create_client, Client, ClientOptions

app = Flask(__name__)
app.secret_key = "money_guardian_key"

# =========================
# Supabase 설정
# =========================
SUPABASE_URL = "https://ibrfukaljdcwsarukknf.supabase.co" 
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlicmZ1a2FsamRjd3NhcnVra25mIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODA4MjU4MSwiZXhwIjoyMDkzNjU4NTgxfQ._jKLrKgnsxU3hjM1mPWKgoQg0waxrfX6erybMhKuUNc"

try:
    options = ClientOptions(postgrest_client_timeout=10)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY, options=options)
except:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route('/')
def index():
    return render_template('index.html')


# =========================
# 인증 (Auth)
# =========================
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    email = data['email']
    
    try:
        res = supabase.table('withdrawn_users') \
            .select("withdrawn_at") \
            .eq("email", email) \
            .order("withdrawn_at", desc=True) \
            .limit(1) \
            .execute()
        
        if res.data:
            withdraw_time_str = res.data[0]['withdrawn_at'].replace('Z', '').split('+')[0]
            withdraw_time = datetime.fromisoformat(withdraw_time_str)
            
            if datetime.now() < withdraw_time + timedelta(days=2):
                diff = (withdraw_time + timedelta(days=2)) - datetime.now()
                hours = int(diff.total_seconds() // 3600)
                return jsonify({
                    "status": "error", 
                    "message": f"탈퇴한 지 얼마 되지 않았습니다. 약 {hours}시간 뒤에 가입 가능합니다."
                }), 400

        supabase.auth.sign_up({
            "email": data['email'],
            "password": data['password'],
            "options": {"data": {"display_name": data['name']}}
        })
        return jsonify({"status": "success", "message": "가입 성공!"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/login', methods=['POST'])
def do_login():
    data = request.json
    try:
        res = supabase.auth.sign_in_with_password({
            "email": data['email'],
            "password": data['password']
        })
        user = res.user
        session['user_id'] = user.id
        session['user_name'] = user.user_metadata.get('display_name', '사용자')
        session['user_email'] = user.email
        
        return jsonify({
            "status": "success", 
            "user_name": session['user_name'],
            "user_email": user.email,
            "joined_at": user.created_at
        })

    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            message = "이메일 또는 비밀번호가 올바르지 않습니다."
        elif "Email not confirmed" in error_msg:
            message = "이메일 인증이 완료되지 않았습니다. 메일함을 확인해 주세요."
        elif "User not found" in error_msg:
            message = "등록되지 않은 이메일입니다."
        else:
            message = "로그인 중 오류가 발생했습니다."
        
        return jsonify({"status": "error", "message": message}), 401


@app.route('/api/reset-password-request', methods=['POST'])
def reset_password_request():
    data = request.json
    email = session.get('user_email') or data.get('email', '').strip()
    
    if not email:
        return jsonify({"status": "error", "message": "이메일을 입력하세요."}), 400
    
    try:
        supabase.auth.reset_password_for_email(email, {
            'redirect_to': 'https://my-banking6-v2-0.onrender.com/reset-password'
        })
        return jsonify({"status": "success", "message": "이메일이 발송되었습니다."})
    except Exception as e:
        error_msg = str(e)
        if "For security purposes" in error_msg or "rate limit" in error_msg.lower():
            message = "요청이 너무 잦습니다. 잠시 후 다시 시도해주세요."
        else:
            message = "이메일 발송 중 오류가 발생했습니다."
        return jsonify({"status": "error", "message": message}), 400

@app.route('/api/logout', methods=['POST'])
def do_logout():
    session.clear()
    try:
        supabase.auth.sign_out()
    except:
        pass
    return jsonify({"status": "success"})
@app.route('/api/reset-password-confirm', methods=['POST'])
def reset_password_confirm():
    data = request.json
    access_token = data.get('access_token')
    refresh_token = data.get('refresh_token')
    new_password = data.get('password')

    if not access_token or not new_password:
        return jsonify({"status": "error", "message": "잘못된 요청입니다."}), 400

    try:
        supabase.auth.set_session(access_token, refresh_token)
        supabase.auth.update_user({"password": new_password})
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": "링크가 만료되었거나 유효하지 않습니다."}), 400

# =========================
# 회원 탈퇴
# =========================
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    
    email = session.get('user_email')
    user_id = session.get('user_id')

    try:
   # ✅ 수정
        supabase.table('withdrawn_users').upsert({
    "email": email,
    "withdrawn_at": datetime.now().isoformat(),  # ← 쉼표 추가!
    "reason": "자진탈퇴"
}, on_conflict="email").execute()
        supabase.auth.admin.delete_user(user_id)
        
        session.clear()
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"탈퇴 에러: {e}")
        return jsonify({"status": "error", "message": "탈퇴 처리 중 오류가 발생했습니다."}), 500

@app.route('/api/clear_all_data', methods=['POST'])
def clear_all_data():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    
    user_id = session['user_id']
    try:
        supabase.table('expenses').delete().eq("user_id", user_id).execute()
        supabase.table('fixed_expenses').delete().eq("user_id", user_id).execute()
        supabase.table('monthly_budgets').delete().eq("user_id", user_id).execute()
        supabase.table('savings').delete().eq("user_id", user_id).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
# =========================
# 지출 (Expenses)
# =========================
@app.route('/api/add_expense', methods=['POST'])
def add_expense():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    data = request.json
    supabase.table('expenses').insert({
        "user_id": session['user_id'],
        "amount": data['amount'],
        "category": data['category'],
        "description": data['description'],
        "expense_date": data['expense_date']
    }).execute()
    return jsonify({"status": "success"})


@app.route('/api/get_expenses', methods=['GET'])
def get_expenses():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    res = supabase.table('expenses').select("*").eq("user_id", session['user_id']).order("expense_date", desc=True).execute()
    return jsonify({"status": "success", "data": res.data})


@app.route('/api/delete_expense', methods=['POST'])
def delete_expense():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    data = request.json
    supabase.table('expenses').delete().eq("id", data['id']).eq("user_id", session['user_id']).execute()
    return jsonify({"status": "success"})


# =========================
# 고정 지출 (Fixed Expenses)
# =========================
@app.route('/api/add_fixed_expense', methods=['POST'])
def add_fixed_expense():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    data = request.json
    supabase.table('fixed_expenses').insert({
        "user_id": session['user_id'],
        "description": data['description'],
        "amount": data['amount'],
        "fixed_date": data['fixed_date']
    }).execute()
    return jsonify({"status": "success"})


@app.route('/api/get_fixed_expenses', methods=['GET'])
def get_fixed_expenses():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    res = supabase.table('fixed_expenses').select("*").eq("user_id", session['user_id']).order("fixed_date").execute()
    return jsonify({"status": "success", "data": res.data})


@app.route('/api/delete_fixed_expense', methods=['POST'])
def delete_fixed_expense():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    data = request.json
    supabase.table('fixed_expenses').delete().eq("id", data['id']).eq("user_id", session['user_id']).execute()
    return jsonify({"status": "success"})


# =========================
# 월별 목표 예산 (Monthly Budgets)
# =========================
@app.route('/api/save_budget', methods=['POST'])
def save_budget():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    data = request.json
    supabase.table('monthly_budgets').upsert({
        "user_id": session['user_id'],
        "budget_month": data['month'],
        "budget_amount": data['amount']
    }, on_conflict="user_id,budget_month").execute()
    return jsonify({"status": "success"})


@app.route('/api/get_budgets', methods=['GET'])
def get_budgets():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    res = supabase.table('monthly_budgets').select("*").eq("user_id", session['user_id']).order("budget_month", desc=True).execute()
    return jsonify({"status": "success", "data": res.data})


@app.route('/api/delete_budget', methods=['POST'])
def delete_budget():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    data = request.json
    supabase.table('monthly_budgets').delete().eq("budget_month", data['month']).eq("user_id", session['user_id']).execute()
    return jsonify({"status": "success"})


# =========================
# 저축 (Savings)
# =========================
@app.route('/api/delete_savings', methods=['POST'])
def delete_savings():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401

    data = request.json

    try:
        supabase.table('savings') \
            .delete() \
            .eq("id", data['id']) \
            .eq("user_id", session['user_id']) \
            .execute()

        return jsonify({"status": "success"})

    except Exception as e:
        print("저축 삭제 오류:", e)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/add_savings', methods=['POST'])
def add_savings():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401

    data = request.json

    try:
        insert_data = {
            "user_id": session['user_id'],
            "amount": int(data['amount']),
            "type": data.get('type', '자유'),
            "description": data.get('description', '')
        }

        supabase.table('savings').insert(insert_data).execute()

        return jsonify({
            "status": "success",
            "message": "저장 완료"
        })

    except Exception as e:
        print("저축 저장 오류:", e)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/get_savings', methods=['GET'])
def get_savings():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401

    try:
        res = (
            supabase.table('savings')
            .select("*")
            .eq("user_id", session['user_id'])
            .order("created_at", desc=True)
            .execute()
        )

        return jsonify({
            "status": "success",
            "data": res.data
        })

    except Exception as e:
        print("저축 조회 오류:", e)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/reset-password')
def reset_password_page():
    return render_template('reset-password.html')



@app.route('/api/add_login_log', methods=['POST'])
def add_login_log():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    data = request.json
    try:
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst).isoformat()
        supabase.table('login_logs').insert({
            "user_id": session['user_id'],
            "device_type": data.get('device_type', '알 수 없음'),
            "browser": data.get('browser', '알 수 없음'),
            "logged_at": now_kst
        }).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/api/get_login_logs', methods=['GET'])
def get_login_logs():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    try:
        res = supabase.table('login_logs') \
            .select("*") \
            .eq("user_id", session['user_id']) \
            .order("logged_at", desc=True) \
            .execute()
        return jsonify({"status": "success", "data": res.data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/add_inquiry', methods=['POST'])
def add_inquiry():
    data = request.json
    try:
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst).isoformat()

        # 입력한 이메일 우선, 없으면 세션 이메일 사용
        user_email = data.get('email') or session.get('user_email', '')
        user_id = session.get('user_id', None)
        user_name = session.get('user_name', '')

        supabase.table('inquiries').insert({
            "user_id": user_id,
            "user_email": user_email,
            "user_name": user_name,
            "title": data.get('title'),
            "content": data.get('content'),
            "created_at": now_kst
        }).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/get_inquiries', methods=['GET'])
def get_inquiries():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    try:
        res = supabase.table('inquiries').select("*") \
            .eq("user_id", session['user_id']) \
            .order("created_at", desc=True) \
            .execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/inquiry')
def inquiry_page():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('inquiry.html')
@app.route('/api/get_faq', methods=['GET'])
def get_faq():
    try:
        res = supabase.table('faq').select("*").order("created_at", desc=True).execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/api/add_faq', methods=['POST'])
def add_faq():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    data = request.json
    try:
        supabase.table('faq').insert({
            "question": data.get('question')
        }).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/find_email', methods=['POST'])
def find_email():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"status": "error", "message": "이름을 입력하세요."}), 400
    try:
        page = 1
        matched = []
        while True:
            users = supabase.auth.admin.list_users(page=page, per_page=1000)
            if not users:
                break
            for u in users:
                if (u.user_metadata or {}).get('display_name', '') == name:
                    matched.append(u)
            if len(users) < 1000:
                break
            page += 1

        if not matched:
            return jsonify({"status": "error", "message": "해당 이름으로 가입된 계정이 없습니다."})

        hints = []
        for u in matched:
            email = u.email
            local, domain = email.split('@')
            hint = local[:2] + '*' * (len(local) - 2) + '@' + domain
            hints.append(hint)

        return jsonify({"status": "success", "hints": hints})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    # =========================
# 관리자 (Admin)
# =========================



ADMIN_ID = "ljy203045"
ADMIN_PW = "15965543"
ADMIN_EMAIL = "ljy203045@gmail.com"

def is_admin():
    return session.get('user_email') == ADMIN_EMAIL and session.get('is_admin') == True

@app.route('/admin/login')
def admin_login_page():
    if is_admin():
        return redirect('/admin')
    return render_template('admin_login.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data.get('id') != ADMIN_ID or data.get('pw') != ADMIN_PW:
        return jsonify({"status": "error"}), 401
    
  
    session['user_email'] = ADMIN_EMAIL
    session['is_admin'] = True
    ua = request.headers.get('User-Agent', '')
    supabase.table('admin_login_log').insert({
        'logged_at': datetime.utcnow().isoformat(),
        'ip': request.remote_addr,
        'device_type': '모바일' if 'Mobi' in ua else 'PC',
        'browser': (
            'Edge' if 'Edge' in ua else
            'Chrome' if 'Chrome' in ua else
            'Firefox' if 'Firefox' in ua else
            'Safari' if 'Safari' in ua else '알 수 없음'
        ),
        'status': 'success'
    }).execute()

    return jsonify({"status": "success"})
@app.route('/api/admin/login_logs')
def admin_login_logs():
    if not session.get('is_admin'):
        return jsonify({'status': 'error', 'message': '권한 없음'}), 403
    
    result = supabase.table('admin_login_log') \
        .select('*') \
        .order('logged_at', desc=True) \
        .limit(50) \
        .execute()
    
    return jsonify({'status': 'success', 'data': result.data})
@app.route('/admin')
def admin_page():
    if not is_admin():
        return redirect('/admin/login')
    return render_template('admin.html')
# 통계

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    try:
        users = supabase.auth.admin.list_users()
        expenses = supabase.table('expenses').select("id", count='exact').execute()
        inquiries = supabase.table('inquiries').select("id", count='exact').eq("status", "답변 대기").execute()
        faqs = supabase.table('faq').select("id", count='exact').execute()
        return jsonify({
            "status": "success",
            "user_count": len(users),
            "expense_count": expenses.count,
            "pending_inquiry_count": inquiries.count,
            "faq_count": faqs.count
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 회원 목록
@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    try:
        response = supabase.auth.admin.list_users()
        seen = set()
        data = []
        for u in response:
            if u.email not in seen:
                seen.add(u.email)
                data.append({
                    "email": u.email,
                    "display_name": (u.user_metadata or {}).get('display_name', '-'),
                    "created_at": str(u.created_at),
                    "last_sign_in_at": str(u.last_sign_in_at) if u.last_sign_in_at else '-',
                    "id": str(u.id)
                })
        # 최근 로그인 순 정렬
        data.sort(key=lambda x: x['last_sign_in_at'] if x['last_sign_in_at'] != '-' else '0', reverse=True)
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 관리자 강제 탈퇴
@app.route('/api/admin/delete_user', methods=['POST'])
def admin_delete_user():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    data = request.json
    user_id = data['user_id']
    email = data['email']
    try:
        supabase.table('expenses').delete().eq("user_id", user_id).execute()
        supabase.table('fixed_expenses').delete().eq("user_id", user_id).execute()
        supabase.table('monthly_budgets').delete().eq("user_id", user_id).execute()
        supabase.table('savings').delete().eq("user_id", user_id).execute()
        supabase.table('login_logs').delete().eq("user_id", user_id).execute()
        supabase.table('inquiries').delete().eq("user_id", user_id).execute()

        supabase.auth.admin.delete_user(user_id)

        supabase.table('withdrawn_users').upsert({
            "email": email,
            "withdrawn_at": datetime.now().isoformat(),
            "reason": "관리자삭제"
       }, on_conflict="email").execute()

        return jsonify({"status": "success"})
    except Exception as e:
        print(f"강제탈퇴 에러: {e}")   # ← 터미널에서 확인
        return jsonify({"status": "error", "message": str(e)}), 500


# 탈퇴 회원 목록
@app.route('/api/admin/withdrawn_users', methods=['GET'])
def admin_withdrawn_users():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    try:
        res = supabase.table('withdrawn_users').select("*").order("withdrawn_at", desc=True).execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/api/admin/withdrawal_stats', methods=['GET'])
def admin_withdrawal_stats():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    try:
        res = supabase.table('withdrawn_users').select("reason").execute()
        voluntary = sum(1 for u in res.data if u.get('reason') == '자진탈퇴')
        forced = sum(1 for u in res.data if u.get('reason') == '관리자삭제')
        return jsonify({
            "status": "success",
            "voluntary": voluntary,
            "forced": forced,
            "total": voluntary + forced
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
# FAQ 답변 등록
@app.route('/api/admin/answer_faq', methods=['POST'])
def admin_answer_faq():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    data = request.json
    try:
        supabase.table('faq').update({
            "answer": data['answer']
        }).eq("id", data['faq_id']).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# FAQ 삭제
@app.route('/api/admin/delete_faq', methods=['POST'])
def admin_delete_faq():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    data = request.json
    try:
        supabase.table('faq').delete().eq("id", data['faq_id']).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 1:1 문의 전체 조회
@app.route('/api/admin/inquiries', methods=['GET'])
def admin_inquiries():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    try:
        res = supabase.table('inquiries').select("*").order("created_at", desc=True).execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 1:1 문의 답변 등록
@app.route('/api/admin/answer_inquiry', methods=['POST'])
def admin_answer_inquiry():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    data = request.json
    try:
        supabase.table('inquiries').update({
            "answer": data['answer'],
            "status": "답변 완료"
        }).eq("id", data['inquiry_id']).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 공지사항 조회
@app.route('/api/admin/notices', methods=['GET'])
def admin_notices():
    try:
        res = supabase.table('notices').select("*").order("created_at", desc=True).execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 공지사항 등록
@app.route('/api/admin/add_notice', methods=['POST'])
def admin_add_notice():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    data = request.json
    try:
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst).isoformat()
        supabase.table('notices').insert({
            "title": data['title'],
            "content": data['content'],
            "is_banner": data.get('is_banner', False),
            "created_at": now_kst
        }).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 공지사항 삭제
@app.route('/api/admin/delete_notice', methods=['POST'])
def admin_delete_notice():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    data = request.json
    try:
        supabase.table('notices').delete().eq("id", data['id']).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return jsonify({"status": "success"})
@app.route('/api/get_notices', methods=['GET'])
def get_notices():
    try:
        res = supabase.table('notices').select("*").order("created_at", desc=True).execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/notice')
def notice_page():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('notice.html')
@app.route('/api/admin/update_notice', methods=['POST'])
def admin_update_notice():
    if not is_admin():
        return jsonify({"status": "error"}), 403
    data = request.json
    try:
        supabase.table('notices').update({
            "title": data['title'],
            "content": data['content'],
            "is_banner": data.get('is_banner', False)
        }).eq("id", data['id']).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/api/change_name', methods=['POST'])
def change_name():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    data = request.json
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({"status": "error", "message": "이름을 입력하세요."}), 400
    try:
        supabase.auth.update_user(
            
            {"data": {"display_name": new_name}}
        )
        session['user_name'] = new_name
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
       

@app.route('/api/get_share_code', methods=['GET'])
def get_share_code():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    try:
        res = supabase.table('share_codes').select("code").eq("user_id", session['user_id']).execute()
        if res.data:
            return jsonify({"status": "success", "code": res.data[0]['code']})
        while True:
            code = str(random.randint(100000, 999999))
            exists = supabase.table('share_codes').select("id").eq("code", code).execute()
            if not exists.data:
                break
        supabase.table('share_codes').insert({
            "user_id": session['user_id'],
            "code": code
        }).execute()
        return jsonify({"status": "success", "code": code})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/view_by_code', methods=['POST'])
def view_by_code():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    data = request.json
    code = data.get('code', '').strip()
    try:
        res = supabase.table('share_codes').select("user_id").eq("code", code).execute()
        if not res.data:
            return jsonify({"status": "error", "message": "존재하지 않는 코드입니다."}), 404

        target_user_id = res.data[0]['user_id']

        if target_user_id == session['user_id']:
            return jsonify({"status": "error", "message": "본인의 코드는 입력할 수 없습니다."}), 400

        target_user = supabase.auth.admin.get_user_by_id(target_user_id)
        user_name = (target_user.user.user_metadata or {}).get('display_name', '사용자')

        expenses = supabase.table('expenses').select("*").eq("user_id", target_user_id).order("expense_date", desc=True).execute()
        savings = supabase.table('savings').select("*").eq("user_id", target_user_id).order("created_at", desc=True).execute()
        budgets = supabase.table('monthly_budgets').select("*").eq("user_id", target_user_id).order("budget_month", desc=True).execute()
        fixed = supabase.table('fixed_expenses').select("*").eq("user_id", target_user_id).order("fixed_date").execute()

        return jsonify({
            "status": "success",
            "user_name": user_name,
            "expenses": expenses.data,
            "savings": savings.data,
            "budgets": budgets.data,
            "fixed_expenses": fixed.data
        })
    except Exception as e:
        print(f"view_by_code 에러: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
if __name__ == '__main__':
    app.run(debug=True, port=5000)