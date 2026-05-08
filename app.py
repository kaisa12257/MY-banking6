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
        # 탈퇴 기록 테이블(withdrawn_users)에서 해당 이메일의 마지막 탈퇴일 조회
        res = supabase.table('withdrawn_users') \
            .select("withdrawn_at") \
            .eq("email", email) \
            .order("withdrawn_at", desc=True) \
            .limit(1) \
            .execute()
        
        if res.data:
            # 문자열 형태의 시간을 파이썬 datetime 객체로 변환
            withdraw_time_str = res.data[0]['withdrawn_at'].replace('Z', '').split('+')[0]
            withdraw_time = datetime.fromisoformat(withdraw_time_str)
            
            # 현재 시간과 비교하여 2일(48시간)이 지났는지 체크
            if datetime.now() < withdraw_time + timedelta(days=2):
                diff = (withdraw_time + timedelta(days=2)) - datetime.now()
                hours = int(diff.total_seconds() // 3600)
                return jsonify({
                    "status": "error", 
                    "message": f"탈퇴한 지 얼마 되지 않았습니다. 약 {hours}시간 뒤에 가입 가능합니다."
                }), 400

        # 탈퇴 기록이 없거나 2일이 지났다면 기존 가입 로직 진행
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
        session['user_email'] = user.email  # 세션에 이메일 저장 (탈퇴 시 사용)
        
        return jsonify({
            "status": "success", 
            "user_name": session['user_name'],
            "user_email": user.email,
            "joined_at": user.created_at  # 가입 날짜 전달
        })
    except:
        return jsonify({"status": "error", "message": "로그인 실패"}), 401

@app.route('/api/logout', methods=['POST'])
def do_logout():
    session.clear()
    try:
        supabase.auth.sign_out()
    except:
        pass
    return jsonify({"status": "success"})
# =========================
# 3. 회원 탈퇴 API 추가
# =========================
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    
    email = session.get('user_email')
    user_id = session.get('user_id')

    try:
        # A. 탈퇴 기록 테이블에 이메일과 현재 시간 저장
        supabase.table('withdrawn_users').insert({
            "email": email,
            "withdrawn_at": datetime.now().isoformat()
        }).execute()

        # B. Supabase Auth에서 유저 삭제 (관리자 권한 필요)
        # 서비스 롤 키를 사용하므로 admin 기능을 쓸 수 있음
        supabase.auth.admin.delete_user(user_id)
        
        session.clear()
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"탈퇴 에러: {e}")
        return jsonify({"status": "error", "message": "탈퇴 처리 중 오류가 발생했습니다."}), 500

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
if __name__ == '__main__':
    app.run(debug=True, port=5000)