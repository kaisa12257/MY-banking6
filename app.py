from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session
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
    email = data.get('email')
    
    try:
        supabase.auth.reset_password_for_email(email, {
            'redirect_to': 'http://127.0.0.1:5000/reset-password'
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


# =========================
# 회원 탈퇴
# =========================
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    
    email = session.get('user_email')
    user_id = session.get('user_id')

    try:
        supabase.table('withdrawn_users').insert({
            "email": email,
            "withdrawn_at": datetime.now().isoformat()
        }).execute()

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
        supabase.table('login_logs').insert({
            "user_id": session['user_id'],
            "device_type": data.get('device_type', '알 수 없음'),
            "browser": data.get('browser', '알 수 없음')
        }).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/get_login_logs', methods=['GET'])
def get_login_logs():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    try:
        res = supabase.table('login_logs').select("*") \
            .eq("user_id", session['user_id']) \
            .order("logged_at", desc=True) \
            .limit(10) \
            .execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
if __name__ == '__main__':
    app.run(debug=True, port=5000)