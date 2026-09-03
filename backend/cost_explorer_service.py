import boto3
from botocore.exceptions import ClientError
from datetime import datetime, date, timedelta

def get_current_month_service_costs():
    """
    Retrieves the unblended AWS costs for the current month, grouped by service.
    Returns a dictionary: {"ServiceName": cost_in_usd_float, ...}
    """
    try:
        session = boto3.Session()
        # CE is a global service endpoint, us-east-1 is standard
        client = session.client('ce', region_name='us-east-1')
        
        today = date.today()
        # Start: 1st of the current month
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        # End: tomorrow (CE requires end date to be exclusive of the reporting period)
        end_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
        
        response = client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )
        
        service_costs = {}
        # Parse the response
        results_by_time = response.get('ResultsByTime', [])
        if results_by_time:
            # We use MONTHLY granularity, so there's usually 1 main entry for the month
            latest_result = results_by_time[0]
            groups = latest_result.get('Groups', [])
            for group in groups:
                keys = group.get('Keys', [])
                service_name = keys[0] if keys else "Unknown"
                
                amount_str = group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', '0')
                try:
                    amount = float(amount_str)
                except ValueError:
                    amount = 0.0
                
                service_costs[service_name] = round(amount, 4)
                
        return service_costs

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "AccessDeniedException":
            print(f"Cost Explorer Access Denied: {e}")
        elif error_code == "DataUnavailableException":
            print(f"Cost Explorer Data Unavailable (Pending): {e}")
            return {"_status": "pending"}
        else:
            print(f"Cost Explorer Client Error: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error retrieving costs: {e}")
        return {}

if __name__ == "__main__":
    print("Testing AWS Cost Explorer Service...")
    costs = get_current_month_service_costs()
    if costs:
        print("\nCurrent Month Costs by Service:")
        for service, cost in costs.items():
            print(f"  {service}: ${cost:.4f}")
        print(f"\nTotal Cost: ${sum(costs.values()):.4f}")
    else:
        print("\nNo cost data returned or an error occurred (see above).")
