import React from 'react';

import {Team, Organization} from 'app/types';
import getDisplayName from 'app/utils/getDisplayName';
import {Client} from 'app/api';

type InjectedTeamsProps = {
  teams: Team[];
  api: Client;
  organization: Organization;
};

type State = {
  teams: Team[];
};

const withUsersTeams = <P extends InjectedTeamsProps>(
  WrappedComponent: React.ComponentType<P>
) =>
  class extends React.Component<
    Omit<P, keyof InjectedTeamsProps> & Partial<InjectedTeamsProps>,
    State
  > {
    static displayName = `withUsersTeams(${getDisplayName(WrappedComponent)})`;

    state = {
      teams: [],
    };

    componentDidMount() {
      this.fetchTeams();
    }

    fetchTeams() {
      this.props
        .api!.requestPromise(this.getUsersTeamsEndpoint())
        .then((data: Team[]) => {
          // console.log('we received');
          // console.log(data);
          this.setState({
            teams: data,
          });
        });
    }

    getUsersTeamsEndpoint() {
      return `/organizations/${this.props.organization!.slug}/teams/`;
    }

    render() {
      return <WrappedComponent {...this.props as P} teams={this.state.teams as Team[]} />;
    }
  };

// createReactClass<Omit<P, keyof InjectedTeamsProps>, State>({
//   displayName: `withUsersTeams(${getDisplayName(WrappedComponent)})`,

//   getInitialState() {
//     // Trigger request to get user's teams
//     console.log(this.props.api);
//     setTimeout(this.setState({teams: [{slug: 'hi'}]}), 2000);
//     return {
//       teams: [],
//     };
//   },

//   render() {
//     return <WrappedComponent {...this.props as P} teams={this.state.teams as Team[]} />;
//   },
// };

export default withUsersTeams;
