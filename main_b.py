# http://localhost:8080/phpmyadmin/

from flask import Flask, request, render_template, jsonify, send_file
import pandas as pd
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from io import BytesIO
import xlsxwriter


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/empdb'  # Configure your database URI
db = SQLAlchemy(app)

machine_data = {}
idle_time_data = {}
active_duration_summary = pd.DataFrame()
idle_duration_summary = pd.DataFrame()
session_duration = 0
session_start_time = None

class Empscreendetail(db.Model):
    # id = db.Column(db.Integer, primary_key=True)
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    machine_name = db.Column(db.String(50), nullable=False, primary_key=True)
    isidle = db.Column(db.String(10), nullable=False)
    duration = db.Column(db.Integer(), nullable=False)
    idle_duration = db.Column(db.Float, nullable=False)
# Initialize an empty list to store employee data

@app.route("/emp_status", methods=["POST"])
def receive_number():
    timestamp = datetime.now()
    data = request.get_json()
    username = data["username"]
    machine_name = data["machine_name"]
    is_idle = data["isIdle"]
    duration = data["duration"]
    idle_duration = data["idle_duration"]
    machine_data[machine_name] = data
    print("Data: ",username, machine_name, is_idle)

    try:
        entry = Empscreendetail(timestamp = timestamp, username = username, machine_name = machine_name, isidle = is_idle, duration = duration, idle_duration = idle_duration)
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        print("ERROR: ", e)

    
    # Update the idle time data
    if username not in idle_time_data:
        idle_time_data[username] = []
    idle_time_data[username].append({"machine_name": machine_name})
    
    return "Data received successfully!"

@app.route("/dashboard")
def dashboard():
    return render_template('dashboard.html')


@app.route("/refresh-table")
def refresh_table():
    status = request.args.get('status')
    print('status: ', status)
    latest_records = db.session.query(Empscreendetail).from_statement(
        db.text("""
        SELECT *
        FROM (
          SELECT *, 
          ROW_NUMBER() OVER (PARTITION BY machine_name ORDER BY timestamp DESC) AS rn
          FROM empscreendetail
        ) t
        WHERE rn = 1
        """)
    ).all()
   
    if status != 'all':
        # current_date = datetime.now().date()
        latest_records = [record for record in latest_records 
                        if (status == 'online' and record.isidle == 'False') 
                        or (status == 'idle' and record.isidle == 'True')
                        or (status == 'offline' and ((datetime.now() - record.timestamp).total_seconds() / 60 > 3))]

    # if username:
    #     latest_records = [record for record in latest_records if record.username == username] 

    current_datetime = datetime.now()   
    return render_template('table_content.html', latest_records=latest_records, current_datetime=current_datetime)

@app.route('/get_username', methods=['POST'])
def get_username():
    print('in get_username function')
    data = request.get_json()
    username = data['username']
    print('username from get_username: ', username)
    latest_records = db.session.query(Empscreendetail).from_statement(
        db.text("""
        SELECT *
        FROM (
          SELECT *, 
          ROW_NUMBER() OVER (PARTITION BY machine_name ORDER BY timestamp DESC) AS rn
          FROM empscreendetail
        ) t
        WHERE rn = 1
        """)
    ).all()
   
    if username:
            latest_records = [record for record in latest_records if record.username == username] 

    current_datetime = datetime.now()   
    print(latest_records)
    return jsonify({
      'latest_records': latest_records,
      'current_datetime': current_datetime
    })

@app.route("/username-graphs")
def username_graphs():
    usernames = db.session.query(Empscreendetail.username).distinct().all()
    print('usernames: ', usernames)
    return render_template('username_graphs.html', usernames=usernames)

@app.route("/graph/<username>")
def graph(username):
    data = db.session.query(Empscreendetail).filter_by(username=username).all()

    # Convert data to Pandas DataFrame
    df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
    } for record in data])

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    df['date'] = df['timestamp'].dt.date

    df['hour'] = df['timestamp'].dt.hour

    idle_data = df[df['isIdle'] == 'True']

    active_data = df[df['isIdle'] == 'False']

    print(df)

    #--------------DAILY CHART--------------

    idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()

    idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)

    active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()

    active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

    print(idle_duration_summary)
    # print(active_duration_summary)

    #--------------HOURLY CHART--------------

    hourly_idle_duration_summary = idle_data.groupby(['date', 'hour'])['duration'].sum().mul(2).reset_index()

    hourly_active_duration_summary = active_data.groupby(['date', 'hour'])['duration'].sum().mul(2).reset_index()

    hourly_idle_dataframes = []

    hourly_active_dataframes = []

    for date in hourly_idle_duration_summary['date'].unique():
        date_df = hourly_idle_duration_summary[hourly_idle_duration_summary['date'] == date]
        date_df['hour_range'] = date_df['hour'].apply(lambda x: f"{x}:00-{x+1}:00")
        date_df.drop('hour', axis=1, inplace=True)
        date_df.rename(columns={'duration': 'idle_duration'})
        date_df['duration'] = (date_df['duration']/60).round(0)
        hourly_idle_dataframes.append(date_df)
        # print(f"Idle Duration for {date}:")                     #date format: 2024-11-06
        # print(date_df)
        # print("\n")

    for date in hourly_active_duration_summary['date'].unique():
        date_df = hourly_active_duration_summary[hourly_active_duration_summary['date'] == date]
        date_df['hour_range'] = date_df['hour'].apply(lambda x: f"{x}:00-{x+1}:00")
        date_df.drop('hour', axis=1, inplace=True)
        date_df.rename(columns={'duration': 'active_duration'})
        date_df['duration'] = (date_df['duration']/60).round(0)
        hourly_active_dataframes.append(date_df)
        

    date_str = [d.isoformat() for d in active_duration_summary['date'].to_list()]

    print('dates_str: ', date_str)

    merged_dataframe = []

    for idle, active in zip(hourly_idle_dataframes, hourly_active_dataframes):
        date = active['date'].iloc[0].isoformat()
        merged_df = pd.merge(active, idle, on=['date', 'hour_range'], suffixes=('_idle', '_active'))
        merged_dataframe.append({'date': date, 'data': merged_df.to_dict()})
        print('date: ', date)

    # print(type(merged_dataframe))
    # for i in merged_dataframe:
    #     print(type(i))
    # df1 = pd.DataFrame()
    # df2 = pd.DataFrame()
    # df3 = pd.DataFrame()
    # test_data = data = [
    #                     {"date": 1, "data": df1.to_dict()},
    #                     {"date": 2, "data": df2.to_dict()},
    #                     {"date": 3, "data": df3.to_dict()}
    #                     ]
    return render_template('graph.html', 
                           username=username, 
                           daily_dates = date_str,
                           daily_active_hours = active_duration_summary['duration_in_hours'].to_list(),
                           daily_idle_hours = idle_duration_summary['duration_in_hours'].to_list(),
                           hourly_merged_dataframe = merged_dataframe,
                        #    json_dataframe = jsonify(merged_dataframe)
                           )

@app.route('/get_dates', methods=['POST'])
def get_dates():
    data = request.get_json()
    start_date = data['start_date']
    end_date = data['end_date']
    username = data['username']
    
    start_date_format = datetime.strptime(start_date, '%m/%d/%Y')
    end_date_format = datetime.strptime(end_date, '%m/%d/%Y').replace(hour=23, minute=59, second=59)

    data = db.session.query(Empscreendetail).filter_by(username=username)

    df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
    } for record in data])

    df = df[df['timestamp'].between(start_date_format, end_date_format)]

    # Process dates as needed
    print('----------------------------------------------------------------')
    print(f"Received dates for user {username}: {start_date_format} to {end_date_format}")
    print('----------------------------------------------------------------')

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    df['date'] = df['timestamp'].dt.date

    df['hour'] = df['timestamp'].dt.hour

    idle_data = df[df['isIdle'] == 'True']

    active_data = df[df['isIdle'] == 'False']

    #--------------DAILY CHART--------------

    idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()

    idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)

    active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()

    active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

    date_str = [d.isoformat() for d in active_duration_summary['date'].to_list()]
    
    return jsonify({'message': 'Dates received successfully',
                    'daily_dates': date_str,
                    'daily_active_hours': active_duration_summary['duration_in_hours'].to_list(),
                    'daily_idle_hours': idle_duration_summary['duration_in_hours'].to_list()
                    })


@app.route('/report', methods=['POST'])
def daily_report():
    report_type = request.form['report_type']
    # print('--------------------------------')
    print('report type: ', report_type)
    
    today = datetime.now()
    today_date = today.strftime("%m/%d/%Y")

    start_date_format = datetime.strptime(today_date, '%m/%d/%Y')
    end_date_format = datetime.strptime(today_date, '%m/%d/%Y').replace(hour=23, minute=59, second=59)

    # print(start_date_format, end_date_format)
    # print('--------------------------------')

    all_usernames = db.session.query(Empscreendetail.username).distinct().all()
    all_usernames = [row[0] for row in all_usernames]
    all_records = []
    for username in all_usernames:
        data = db.session.query(Empscreendetail).filter_by(username=username)
        df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
                            } for record in data])
        
        if report_type == 'daily':

            df = df[df['timestamp'].between(start_date_format, end_date_format)]

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['date'] = df['timestamp'].dt.date
            df['hour'] = df['timestamp'].dt.hour
            idle_data = df[df['isIdle'] == 'True']
            active_data = df[df['isIdle'] == 'False']
            idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
            idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)
            active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
            active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

            username = username
            machine_name = df['machine_name'].to_list()[0]
            login_time = df.head(1)['timestamp'].iloc[0]
            logoff_time = df.tail(1)['timestamp'].iloc[0]
            total_productive_hours = sum(active_duration_summary['duration_in_hours'].to_list())
            total_non_productive_hours = sum(idle_duration_summary['duration_in_hours'].to_list())
            total_system_time = round(total_productive_hours + total_non_productive_hours, 1)
            

            all_records.append([username, machine_name, login_time, logoff_time, total_system_time, total_productive_hours,
                                total_non_productive_hours])
            
            return render_template('daily_report.html', all_records = all_records, date = today_date)
        
        elif report_type == 'custom':
            print('in custom report')
            return render_template('custom_report.html', all_records = all_records)
        
        elif report_type == 'custom_day':
            print('in custom day report')
            return render_template('custom_day_report.html', all_records = all_records)



        # print('--------------------------------')
        # print('username: ', username)
        # print('machine_name: ', machine_name)
        # print('login_time: ', login_time)
        # print('logoff_time: ', logoff_time)
        # print('total_system_time: ', total_system_time)
        # print('total_productive_hours: ', total_productive_hours)
        # print('total_non_productive_hours: ', total_non_productive_hours)
        # print('--------------------------------')

    # return render_template('daily_report.html', all_records = all_records, date = today_date)

@app.route('/download-report', methods=['POST'])
def download_report():
    # You can reuse the logic from your daily_report function
    today = datetime.now()
    today_date = today.strftime("%m/%d/%Y")
    
    start_date_format = datetime.strptime(today_date, '%m/%d/%Y')
    end_date_format = datetime.strptime(today_date, '%m/%d/%Y').replace(hour=23, minute=59, second=59)

    all_usernames = db.session.query(Empscreendetail.username).distinct().all()
    all_usernames = [row[0] for row in all_usernames]
    all_records = []
    for username in all_usernames:
        data = db.session.query(Empscreendetail).filter_by(username=username)
        df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
                            } for record in data])

        df = df[df['timestamp'].between(start_date_format, end_date_format)]
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        idle_data = df[df['isIdle'] == 'True']
        active_data = df[df['isIdle'] == 'False']
        idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)
        active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

        username = username
        machine_name = df['machine_name'].to_list()[0]
        login_time = str(df.head(1)['timestamp'].iloc[0])
        logoff_time = str(df.tail(1)['timestamp'].iloc[0])
        total_productive_hours = sum(active_duration_summary['duration_in_hours'].to_list())
        total_non_productive_hours = sum(idle_duration_summary['duration_in_hours'].to_list())
        total_system_time = round(total_productive_hours + total_non_productive_hours, 1)

        all_records.append([username, machine_name, login_time, logoff_time, total_system_time, total_productive_hours,
                            total_non_productive_hours])

    # Create an Excel file
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    # Write header
    worksheet.write_row(0, 0, ['Username', 'Machine Name', 'Log-in Time', 'Log-off Time', 'Total System Time (Hr.)', 'Total Productive Hours', 'Total Non-Productive Hours'])

    # Write data
    for i, record in enumerate(all_records):
        worksheet.write_row(i + 1, 0, record)

    workbook.close()
    output.seek(0)

    # Send the file to the user
    return send_file(
        output,
        as_attachment=True,
        download_name='daily_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# /get_dates_for_report
@app.route('/get_dates_for_report', methods=['POST'])
def get_dates_for_report():
    print('in get_dates_for_report function')
    data = request.get_json()
    start_date = data['start_date']
    end_date = data['end_date']
    start_date_format = datetime.strptime(start_date, '%m/%d/%Y')
    end_date_format = datetime.strptime(end_date, '%m/%d/%Y').replace(hour=23, minute=59, second=59)

    print(start_date_format, end_date_format)

    all_records = []

    all_usernames = db.session.query(Empscreendetail.username).distinct().all()
    all_usernames = [row[0] for row in all_usernames]
    all_records = []
    for username in all_usernames:
        data = db.session.query(Empscreendetail).filter_by(username=username)
        df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
                            } for record in data])

        df = df[df['timestamp'].between(start_date_format, end_date_format)]
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        idle_data = df[df['isIdle'] == 'True']
        active_data = df[df['isIdle'] == 'False']
        idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)
        active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

        username = username
        machine_name = df['machine_name'].to_list()[0]

        total_productive_hours = round(sum(active_duration_summary['duration_in_hours'].to_list()), 1)
        total_non_productive_hours = round(sum(idle_duration_summary['duration_in_hours'].to_list()), 1)
        total_system_time = round(total_productive_hours + total_non_productive_hours, 1)

        all_records.append([username, machine_name, total_system_time, total_productive_hours,
                            total_non_productive_hours])
        
    # return render_template('custom_report.html', all_records = all_records, date = [start_date, end_date])
    print('all record: ', all_records)
    return jsonify({'all_records': all_records,
                    'date': [start_date_format, end_date_format]})


@app.route('/download-custom_report', methods=['POST'])
def download_custom_report():
    print('in download_custom_report')
    data = request.get_json()
    start_date = data['start_date']
    end_date = data['end_date']
    start_date_format = datetime.strptime(start_date, '%m/%d/%Y')
    end_date_format = datetime.strptime(end_date, '%m/%d/%Y').replace(hour=23, minute=59, second=59)

    print(data)
    print(start_date_format, end_date_format)

    all_records = []

    all_usernames = db.session.query(Empscreendetail.username).distinct().all()
    all_usernames = [row[0] for row in all_usernames]
    for username in all_usernames:
        data = db.session.query(Empscreendetail).filter_by(username=username)

        df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
                            } for record in data])

        df = df[df['timestamp'].between(start_date_format, end_date_format)]
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        print(df)
        idle_data = df[df['isIdle'] == 'True']
        active_data = df[df['isIdle'] == 'False']
        idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)
        active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

        username = username
        machine_name = df['machine_name'].to_list()[0]

        total_productive_hours = round(sum(active_duration_summary['duration_in_hours'].to_list()), 1)
        total_non_productive_hours = round(sum(idle_duration_summary['duration_in_hours'].to_list()), 1)
        total_system_time = round(total_productive_hours + total_non_productive_hours, 1)

        all_records.append([username, machine_name, total_system_time, total_productive_hours,
                            total_non_productive_hours])
        
    print('----------------------------------------------------------------')
    print('before download custom report: ', all_records)
    print(all_records)
    print('----------------------------------------------------------------')
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    # Write header
    worksheet.write_row(0, 0, ['Username', 'Machine Name', 'Total System Time (Hr.)', 'Total Productive Hours', 'Total Non-Productive Hours'])

    # Write data
    for i, record in enumerate(all_records):
        worksheet.write_row(i + 1, 0, record)

    workbook.close()
    output.seek(0)

    # Send the file to the user
    return send_file(
        output,
        as_attachment=True,
        download_name='custom_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/custom_day_report', methods=['POST'])
def custom_day_report():
    data = request.get_json()
    start_date = data['start_date']
    start_date_format = datetime.strptime(start_date, '%m/%d/%Y')
    end_date_format = datetime.strptime(start_date, '%m/%d/%Y').replace(hour=23, minute=59, second=59)
    all_records = []

    all_usernames = db.session.query(Empscreendetail.username).distinct().all()
    all_usernames = [row[0] for row in all_usernames]
    all_records = []
    for username in all_usernames:
        data = db.session.query(Empscreendetail).filter_by(username=username)
        df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
                            } for record in data])

        df = df[df['timestamp'].between(start_date_format, end_date_format)]
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        idle_data = df[df['isIdle'] == 'True']
        active_data = df[df['isIdle'] == 'False']
        idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)
        active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

        username = username
        machine_name = df['machine_name'].to_list()[0]

        total_productive_hours = round(sum(active_duration_summary['duration_in_hours'].to_list()), 1)
        total_non_productive_hours = round(sum(idle_duration_summary['duration_in_hours'].to_list()), 1)
        total_system_time = round(total_productive_hours + total_non_productive_hours, 1)

        all_records.append([username, machine_name, total_system_time, total_productive_hours,
                            total_non_productive_hours])
        
    # return render_template('custom_report.html', all_records = all_records, date = [start_date, end_date])
    print('all record: ', all_records)
    return jsonify({'all_records': all_records,
                    'date': [start_date_format, end_date_format]})


@app.route('/download-custom_day_report', methods=['POST'])
def download_custom_day_report():
    data = request.get_json()
    start_date = data['start_date']
    start_date_format = datetime.strptime(start_date, '%m/%d/%Y')
    end_date_format = datetime.strptime(start_date, '%m/%d/%Y').replace(hour=23, minute=59, second=59)
    all_records = []
    all_usernames = db.session.query(Empscreendetail.username).distinct().all()
    all_usernames = [row[0] for row in all_usernames]
    all_records = []
    for username in all_usernames:
        data = db.session.query(Empscreendetail).filter_by(username=username)
        df = pd.DataFrame([{
        'timestamp': record.timestamp,
        'username': record.username,
        'machine_name': record.machine_name,
        'duration': record.duration,
        'isIdle': record.isidle,
        'idle_duration': record.idle_duration
                            } for record in data])

        df = df[df['timestamp'].between(start_date_format, end_date_format)]
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        idle_data = df[df['isIdle'] == 'True']
        active_data = df[df['isIdle'] == 'False']
        idle_duration_summary = idle_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        idle_duration_summary['duration_in_hours'] = ((idle_duration_summary['duration'])/3600).round(2)
        active_duration_summary = active_data.groupby(['date', 'username'])['duration'].sum().mul(2).reset_index()
        active_duration_summary['duration_in_hours'] = ((active_duration_summary['duration'])/3600).round(2)

        username = username
        machine_name = df['machine_name'].to_list()[0]
        login_time = str(df.head(1)['timestamp'].iloc[0])
        logoff_time = str(df.tail(1)['timestamp'].iloc[0])
        total_productive_hours = sum(active_duration_summary['duration_in_hours'].to_list())
        total_non_productive_hours = sum(idle_duration_summary['duration_in_hours'].to_list())
        total_system_time = round(total_productive_hours + total_non_productive_hours, 1)

        all_records.append([username, machine_name, login_time, logoff_time, total_system_time, total_productive_hours,
                            total_non_productive_hours])

    # Create an Excel file
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    # Write header
    worksheet.write_row(0, 0, ['Username', 'Machine Name', 'Log-in Time', 'Log-off Time', 'Total System Time (Hr.)', 'Total Productive Hours', 'Total Non-Productive Hours'])

    # Write data
    for i, record in enumerate(all_records):
        worksheet.write_row(i + 1, 0, record)

    workbook.close()
    output.seek(0)

    # Send the file to the user
    return send_file(
        output,
        as_attachment=True,
        download_name='custom_day_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )




if __name__ == "__main__":
    app.run(debug=True)